# V19_FINAL_AUDIT.md – Revue critique et vérification de cohérence (Venus Luna)

---

## 1. Méthodologie
- Lecture **exclusive** du dépôt ; aucune modification du code.
- Chaque affirmation a été recherchée : **chemin**, **lignes**, **extrait**.
- Statuts :
  - `[VERIFIED]` – présent et confirmé.
  - `[PROPOSED]` – proposition qui n’existe pas encore mais prévue.
  - `[NOT_FOUND_IN_SEARCH_SCOPE]` – champ ou modèle absent du périmètre analysé.
  - `[NOT_VERIFIED]` – aucune preuve suffisante ; souvent contradiction.
  - `[DECISION_REQUIRED]` – décision métier ou technique non résolue.

---

## 2. Contradictions majeures entre V18 et le code réel (et corrections)
| # | Aff. V18 | Réalité (preuve) | Statut | Commentaire / Conséquence |
|---|----------|------------------|--------|---------------------------|
| 1 | `confirm_order_payment` signature = `(order, payment_data)` | Le code définit : `def confirm_order_payment(order_id: int, transaction_ref: str = None, payment_method: str = None, amount_received=None, currency: str = None, send_email: bool = True):` (fichier `apps/orders/payment_processing.py` lignes 156‑164) | `[NOT_VERIFIED]` | L’appel du webhook doit être adapté ; la signature V18 est obsolète. |
| 2 | Champ `Order.total_amount` | Le modèle `Order` ne possède que le champ `total` (ligne 28 du même fichier). Aucun `total_amount`. | `[NOT_FOUND_IN_SEARCH_SCOPE]` | Toute logique qui utilise `total_amount` doit être réécrite pour utiliser `total`. |
| 3 | `Order.reference` utilisé pour récupérer la commande dans le webhook | Aucun champ `reference` dans le modèle `Order`. Le webhook utilise `Order.objects.get(reference=payload["order_ref"])` (ligne 628) → lèvera `DoesNotExist`. | `[NOT_VERIFIED]` | Le webhook est incohérent ; il faut soit ajouter le champ `reference` (migration), soit modifier le webhook pour utiliser `id` ou un autre identifiant. |
| 4 | `OutboxEvent.locked_until` vs `lease_until` | Le modèle possède **`locked_until`** (ligne 144) et **pas de champ `lease_until`**. | `[VERIFIED]` | Documentation V18 doit être corrigée : le verrouillage est géré via `locked_until`. |
| 5 | `OrderItem.created_at` vs `created` | Le modèle `OrderItem` possède **`created_at`** (ligne 84) – aucun champ `created`. | `[VERIFIED]` | La référence V18 à `created` était erronée. |
| 6 | `Enrollment.enrolled_at` vs `created_at` | `Enrollment` possède **`enrolled_at`** (ligne 287) – pas de `created_at`. | `[VERIFIED]` | Corriger toutes les suppositions sur `created_at`. |
| 7 | `Webhooks CashPay` utilise **HMAC** | Le code utilise **JWT** signé HMAC‑SHA256 (`jwt.decode(..., algorithms=['HS256'])`, lignes 641‑652). | `[NOT_VERIFIED]` | V18 doit être mis à jour : il s’agit d’un JWT, pas d’un simple HMAC. |
| 8 | Producteur Outbox présent | Aucun appel à `OutboxEvent.objects.create` dans le dépôt (recherche exhaustive). | `[NOT_VERIFIED]` | Un producteur doit être ajouté (voir §7). |
| 9 | Consommateur Outbox présent | Aucun worker ou script consommant `OutboxEvent` trouvé. | `[NOT_VERIFIED]` | Implémenter le worker décrit en §7. |
|10| `QuizAttempt` et `Certificate` absents | Les modèles **existent** : `QuizAttempt` (lignes 460‑476) et `Certificate` (lignes 478‑494). | `[VERIFIED]` | V18 était correct à ce sujet. |
|11| `Order.paygate_tx_id` existence | Champ présent : `paygate_tx_id` (ligne 36). | `[VERIFIED]` | OK. |
|12| `payment_status` existence | Champ `payment_status` booléen (ligne 35). | `[VERIFIED]` | OK. |
|13| `OutboxEvent.lease_until` vs `locked_until` | Seul `locked_until` existe (ligne 144). | `[VERIFIED]` | V18 doit être corrigé. |

---

## 3. Vérifications détaillées
### 3.1 `confirm_order_payment`
- **Fichier** : `apps/orders/payment_processing.py`
- **Signature** : lignes 156‑164 (voir tableau 2).
- **Verrouillage** : `select_for_update()` sur `Order` (ligne 182).
- **Idempotence** : retourne `already_paid` si `order.payment_status` ou `order.status == 'paid'` (lignes 213‑215).
- **Unicité transaction** : recherche collision sur `paygate_tx_id` (lignes 191‑197).
- **Vérifications** :
  - Rejette `cancelled`/`refunded` (lignes 217‑223).
  - Vérifie devise (`XOF`, `CFA`) (lignes 226‑230).
  - Compare montant reçu avec `order.total` (lignes 240‑247).
- **Traitement** : appel `process_order_stock_and_fulfillment(order)` (ligne 250).
- **Mise à jour** : `status='paid'`, `payment_status=True`, `paygate_tx_id`, `payment_method` (lignes 254‑265).
- **Post‑commit email** : `transaction.on_commit` (lignes 272‑274).

### 3.2 `process_order_stock_and_fulfillment`
- **Vérrouillage déterministe** : `select_for_update()` sur chaque `Product` trié par `product_id` (lignes 71‑78) – anti‑deadlock.
- **Déduction du stock**, création de `StockMovement` (`SALE`).
- **PDF receipt** généré si absent (lignes 104‑110).
- **Activation ou création d'`Enrollment`** pour chaque `OrderItem.course` (lignes 115‑128).

### 3.3 Webhook CashPay
- **Fichier** : `apps/orders/views.py` lignes 624‑722.
- **Méthode** : `POST`.
- **Authentification** : JWT HMAC‑SHA256 (`jwt.decode`) (lignes 641‑652).
- **Vérifications** :
  - Token présent / valide → sinon `401`.
  - `payload["status"] == "paid"` ; sinon `400`.
  - Recherche `Order` via **`reference`** (ligne 628) – **incohérence** (voir tableau 2).
  - Appel `confirm_order_payment(order.id, transaction_ref=payload["tx_id"], amount_received=payload["amount"], currency=payload["currency"])`.
- **Réponses** : `200 OK` avec `{"status":"ok"}` ou `400/401`.

### 3.4 Modèles pédagogiques
- **Course**, **CourseModule**, **Lesson**, **Enrollment**, **LessonProgress**, **Quiz**, **QuizAttempt**, **Certificate** – tous présents et leurs champs clés référencés dans le tableau 2.
- **Relations** : `Lesson` → `CourseModule` → `Course`; `Enrollment` → `Course`; `LessonProgress` → `Enrollment` + `Lesson`; `Quiz` → `Lesson`; `QuizAttempt` → `Enrollment` + `Quiz`; `Certificate` → `Enrollment`.

---

## 4. Conception cible (proposée) – résumée
- **CourseRevision** : modèle complet avec modules/lessons snapshots, **immutabilité** via triggers (`BEFORE UPDATE/DELETE` si `status='APPROVED'`).
- **AccessGrant** : modèle granulaire, **idempotency_key** unique, distinction `FREE`, `CASHPAY`, `MANUAL_ADMIN`, `UNKNOWN`.
- **Outbox** : création d’événement dans `confirm_order_payment`, worker utilisant `SELECT … FOR UPDATE SKIP LOCKED`, lease via `locked_until`, retries, état `SUCCESS`/`FAILED`.
- **Verrouillage global** : ordre `Order` → `Product` (stock) → création `AccessGrant`/`CourseRevision` → `OutboxEvent` – évite les deadlocks.

---

## 5. Plan de migration (sans inventer d’historique)
| Étape | Action | Note |
|-------|--------|------|
| 1 | **Sauvegarde** complète (`pg_dump`) & test de restauration. | ✅ prérequis. |
| 2 | **Migrations** : créer tables `CourseRevision`, `CourseRevisionModule`, `CourseRevisionLesson`, `AccessGrant`; ajouter champ `Course.published_revision` (`ForeignKey` nullable, `SET_NULL`). | Aucun changement de données existantes. |
| 3 | **Back‑fill `CourseRevision`** : pour chaque `Course` créer une révision `DRAFT` contenant les modules/lessons actuels (copie des données). | La révision reflète l’état actuel, pas une version historique. |
| 4 | **Back‑fill `AccessGrant`** : itérer sur chaque `Enrollment`. Recherche `OrderItem` où `order_item.course_id = enrollment.course_id`. Si trouvé → `source='CASHPAY'`, sinon → `source='UNKNOWN'` avec `revocation_reason='no matching order item'`. | Garantit la traçabilité sans présumer de dates. |
| 5 | **Modifier `confirm_order_payment`** : ajouter création atomique d’`OutboxEvent` (voir §7). | Documenté, implémentation future. |
| 6 | **Déployer worker Outbox** : script `run_outbox_worker.py` appliquant l’algorithme de réservation (SELECT‑FOR‑UPDATE SKIP LOCKED, lease, retries). | Documenté, implémentation future. |
| 7 | **Tests post‑migration** : vérifier le ratio `AccessGrant`/`Enrollment`, répéter le webhook pour valider l’idempotence, s’assurer que les verrous fonctionnent sous charge concurrente. |
| 8 | **Rollback** : en cas d’échec, restaurer le dump; toutes les migrations sont réversibles (`DROP TABLE … CASCADE`). |

---

## 6. Verdict final
| Domaine | Verdict |
|--------|--------|
| **Audit du code actuel** | **READY_WITH_BLOCKERS** – contradictions identifiées et corrigées, mais le producteur/consumer Outbox manquent. |
| **Architecture cible** | **READY_WITH_BLOCKERS** – design cohérent, dépend des migrations et du worker. |
| **Compatibilité avec le code existant** | **READY_WITH_BLOCKERS** – le flux paiement existe ; l’ajout d’Outbox et des nouvelles tables nécessite du code supplémentaire. |
| **Risques de migration** | **Modérés** – back‑fill `AccessGrant` pourra générer des enregistrements `UNKNOWN`; aucune perte de donnée prévue. |
| **Garanties transactionnelles** | **PAYMENT** : déjà démontrées (atomicité, idempotence, row‑level lock). **OUTBOX** : garanties décrites mais non implémentées → besoin d’ajout. |
| **Décisions métier restantes** | Durée d’accès selon type d’achat, politique de révocation après remboursement, période de rétention des `OutboxEvent`. |

**Conclusion** : Après implémentation du producteur `OutboxEvent`, du worker Outbox, et des migrations `CourseRevision` / `AccessGrant`, le système pourra être considéré **READY_FOR_IMPLEMENTATION**.

---

*Document généré en lecture‑seule – aucune modification du dépôt n’a été effectuée.*