# Paiement CashPay, capture de révision et Outbox

> Aligné sur le code livré le 2026-11-23 (`apps/orders/payment_processing.py`, `apps/orders/outbox.py`,
> `apps/orders/views.py`).

## 1. Flux CashPay

```
buy_course / checkout ──► Order(pending) ──► CashPay Link2Pay (merchant_reference = order.id,
                                              order_reference CashPay stockée dans paygate_tx_id)
                     ┌──────────── webhook JWT (HS256) ─────────────┐
CashPay ─────────────┤                                              ├──► confirm_provider_payment()
                     └── polling page relais / page retour (API) ───┘          │
                                                                               ▼
                                                                  confirm_order_payment()  [1 transaction]
```

`buy_course` refuse désormais une formation sans révision publiée (décision R3).

## 2. Validation prestataire

| Contrôle | Webhook | Polling / retour (GET /orders/{reference}) |
|---|---|---|
| Authenticité | JWT HS256 vérifié avec `CASHPAY_SECRET_WEBHOOK` (fail-closed si absent) | appel authentifié OAuth à l'API |
| Commande | `merchant_reference` (= id) ; à défaut `order_reference` = `paygate_tx_id` | référence stockée |
| État | `Paid` seul confirme ; `Partial`/`Excess` → réconciliation | idem + `Canceled/Error` → annulation conditionnelle, `Expired` |
| Montant | **exact** : `billed_amount`, sinon `amount` s'il égale le total, sinon vérification API | `billed_amount` = total **et** `amount` (reste dû) = 0 |
| Devise | `XOF` uniquement (ISO 4217) | idem |
| Référence | unique entre commandes ; jamais remplacée | idem |
| Rejeu | sans effet : commande déjà payée → `already_paid`, `paid_at` inchangé | idem |

Changements de comportement : le trop-perçu et la devise « CFA » sont refusés ; un polling qui
ne fournit pas `billed_amount` ne confirme plus (incident `AMOUNT_UNVERIFIED`).

## 3. Confirmation interne (`confirm_order_payment`) — une transaction

1. `SELECT … FOR UPDATE` sur `Order`.
2. Référence (collision, incohérence), idempotence, état irréversible, devise, montant exact.
3. `process_order_stock_and_fulfillment` :
   - **capture** (`capture_course_revisions`) : formations verrouillées une à une par id croissant,
     lecture de `Course.published_revision` **après** verrou, création de `PaymentRevisionLink`
     puis `AccessGrant` (+ inscription) par ligne ;
   - stock : produits verrouillés par id croissant, déduction, mouvements SALE ;
   - événement Outbox `PDF_RECEIPT`.
4. `status=paid`, `payment_status=True`, `paid_at` (si NULL uniquement), référence.
5. Événement Outbox `PAYMENT_EMAIL`.

Si une étape échoue, tout est annulé (aucun lien, droit ou événement). Les erreurs ne sont plus
absorbées (l'ancien `try/except` autour des inscriptions a été supprimé).

Le même traitement (sans email) s'applique quand l'administration passe une commande à
« payé » (signal `post_save`, action « Retraiter le stock ») : source `admin_fulfillment`.

## 4. PaymentRevisionLink

`order`, `order_item` (OneToOne → une ligne ne peut être liée qu'à une révision), `course`
(copie figée : `OrderItem.course` est `SET_NULL`), `course_revision`, `source`
(`payment_confirmation` / `admin_fulfillment` / `reconciliation`), `captured_at`, `captured_by`.
FK composite PostgreSQL : la révision appartient à la formation.

Jamais de « dernière révision approuvée » : seule `Course.published_revision` lue sous verrou est utilisée.

## 5. Réconciliation (`PaymentReconciliation`)

Un rollback SQL n'annule pas un paiement externe. Les incidents sont enregistrés **hors** de la
transaction en échec (ou dans la transaction de confirmation quand le paiement est valide) et
dédupliqués tant qu'ils sont ouverts (`dedup_key`, `occurrences`).

| Type | Déclencheur | Traitement |
|---|---|---|
| `confirmation_failed` | Paid reçu mais confirmation interne en erreur (stock, référence…) ; commande sans utilisateur | corriger la cause puis relancer (retraitement admin ou nouvelle notification) |
| `amount_mismatch` | montant/devise ≠ commande | vérifier dans CashPay, rembourser si besoin |
| `amount_unverified` | montant non vérifiable | vérifier dans CashPay |
| `provider_state` | Partial, Excess, Reviewed, Refunded… | traitement manuel |
| `paid_on_closed_order` | Paid sur commande annulée/remboursée | rembourser ou réouvrir |
| `no_published_revision` | ligne de formation sans révision publiée | publier une révision puis action admin « Capturer la révision publiée et attribuer l'accès » |
| `duplicate_purchase` | droit actif déjà existant | rembourser l'achat en double si nécessaire |

## 6. Outbox et worker

- Événements : `PDF_RECEIPT` (`pdf-receipt:order:<id>`), `PAYMENT_EMAIL` (`payment-email:order:<id>`).
  `COURSE_ENROLLMENT` (type préexistant) n'est pas utilisé : le droit d'accès est créé de façon
  synchrone et atomique dans la transaction de paiement (aucun worker n'est déployé aujourd'hui ;
  un accès différé dégraderait le parcours d'achat).
- Dispatch immédiat après commit (`transaction.on_commit`, désactivable par
  `OUTBOX_EAGER_DISPATCH=False`) : comportement historique conservé (reçu et email juste après paiement).
- Worker : `python manage.py process_outbox --once` (planifié) ou `--loop`.
  - réclamation `SELECT … FOR UPDATE SKIP LOCKED` en transaction courte, puis lease
    (`locked_until`, `lease_token`) — verrou SQL relâché avant traitement ;
  - lease expirée ⇒ l'événement redevient réclamable ; l'ancien worker ne peut plus le clore ;
  - aucune remise à zéro en masse des événements PROCESSING ;
  - `OUTBOX_LEASE_SECONDS=300` (> PDF + Cloudinary + SMTP avec timeouts) ;
  - `OUTBOX_MAX_ATTEMPTS=8`, backoff 30 s × 2ⁿ plafonné à 1 h (~4 h de panne absorbée) ;
  - erreur définitive (`PermanentOutboxError` : générateur PDF absent, pas d'email) → FAILED ;
  - admin : liste des événements, action « Remettre en file » pour les FAILED.

## 7. Idempotence — trois niveaux

| Niveau | Garantie |
|---|---|
| Événement | `uniq_outbox_idempotency_key` |
| Effet métier | `PaymentRevisionLink.order_item` OneToOne ; `AccessGrant.order_item` OneToOne ; `uniq_accessgrant_active_nonpurchase` ; reçu déjà présent ignoré ; `paid_at` écrit si NULL |
| Concurrence | verrou `Order` ; verrous `Course` puis `Product` (id croissant) ; SKIP LOCKED + lease |

Email : livraison « au moins une fois » (un worker tué après l'envoi et avant la clôture peut renvoyer l'email).

## 8. Ordre global de verrouillage

```
Order  →  Course (id croissant)  →  Product (id croissant)
```
- Paiement / traitement admin : Order, puis Course, puis Product.
- Publication : Course seul (la révision APPROVED, immuable, n'est pas verrouillée).
- Transitions de revue : CourseRevision seule.
- Révocation : Order seul.
Aucune fonction n'acquiert ces verrous dans un autre ordre. Le verrou Course synchronise
capture et publication : un paiement concurrent à une publication capture la révision publiée
au commit de celle-ci (testé sur PostgreSQL).

## 9. Points ouverts côté intégration CashPay

- La documentation indique une vérification du JWT de rappel « avec votre clé API » ; le code
  utilise `CASHPAY_SECRET_WEBHOOK`. À confirmer auprès de SEMOA (inchangé).
- Le contenu exact des claims du JWT (présence de `billed_amount`, `currency`, `exp`, `jti`) n'est
  pas documenté : le code vérifie via l'API quand le montant est absent ou ambigu.
