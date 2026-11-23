# Rapport d'implémentation — Versionnement LMS, paiement et Outbox

Date : 2026-11-23 · Mode : développement local uniquement · Aucun commit, push, déploiement
ni migration de production n'a été effectué.

**Verdict : READY_FOR_TESTING** — implémentation terminée et testée (190/190 sur PostgreSQL
local), mais validation fonctionnelle, intégration CashPay réelle, revue de code et décisions de
déploiement restent nécessaires (§6).

## 1. Ce qui existait avant

- `Course` / `CourseModule` / `Lesson` / `Quiz`… édités en place et servis directement aux apprenants ; aucun versionnement.
- `Enrollment` unique (user, course) dont la commande était écrasée au réachat.
- `QuizAttempt` sans réponses enregistrées (score seul).
- `confirm_order_payment` (fichier non versionné) : verrou commande + verrous produits corrects,
  mais erreurs d'inscription absorbées, montant contrôlé par `<` seulement, devise facultative,
  PDF/Cloudinary généré pendant les verrous, pas de `paid_at`.
- Polling CashPay confirmant sans vérifier le montant (et `amount` = reste dû sur cet endpoint).
- Modèle `OutboxEvent` présent mais ni producteur ni worker ; aucune infrastructure asynchrone.
- 144 tests ; 1 échec sur SQLite (`test_06`, conçu pour PostgreSQL).

## 2. Ce qui a été implémenté

| Domaine | Réalisation |
|---|---|
| Versionnement | `CourseRevision` (snapshot JSON + empreinte), `CourseRevisionEvent`, `Course.published_revision` |
| Workflow | `apps/courses/revisions.py` : brouillon, soumission (gel), retrait, approbation, rejet motivé, publication explicite ; permissions dédiées |
| Intégrité | immuabilité applicative + triggers PostgreSQL ; FK composites « même formation » ; contraintes CHECK/UNIQUE |
| Contenu apprenant | `apps/courses/content.py` : lecteur, catalogue, fiche, progression, quiz servis depuis la révision |
| Accès | `AccessGrant` + `apps/courses/access.py` : un droit par ligne d'achat, gratuit/manuel, révocation historisée |
| Historique | `QuizAttempt.attempt_snapshot`, `revision` sur tentatives/progressions/inscriptions, page de détail d'une tentative |
| Paiement | montant exact, devise XOF, `paid_at` unique, capture sous verrou Course, `PaymentRevisionLink`, réconciliation |
| CashPay | webhook : recherche de commande corrigée, Partial/Excess, vérification API si montant ambigu ; polling : `billed_amount`/reste dû, annulation conditionnelle ; payload brut retiré des logs |
| Outbox | production atomique (reçu, email), dispatch post-commit, worker `process_outbox` (SKIP LOCKED, lease, retry, backoff, FAILED) |
| Admin | révisions (boutons de workflow, comparaison, contenu figé, historique), droits d'accès (révocation), réconciliations (capture différée, résolution), outbox (remise en file), `paid_at` |
| Reprise | révision n°1 publiée pour l'existant ; aucune donnée historique inventée |
| Tests | 46 nouveaux tests ; configuration `settings_pg_test` (PostgreSQL local) |

## 3. Fichiers

**Nouveaux** : `apps/courses/{content,revisions,access,testing,tests_versioning}.py`,
`apps/courses/migrations/0002…0004`, `apps/orders/{outbox,tests_payment_capture}.py`,
`apps/orders/management/commands/process_outbox.py`, `apps/orders/migrations/0009, 0010`,
`config/settings_pg_test.py`, `templates/courses/quiz_attempt_detail.html`,
`templates/admin/courses/courserevision/{change_form,workflow_confirm}.html`,
`docs/{ARCHITECTURE_LMS,PAYMENT_AND_OUTBOX,DATABASE_MIGRATION_PLAN,TESTING_STRATEGY,IMPLEMENTATION_REPORT}.md`.

**Modifiés par ce chantier** : `apps/courses/{models,services,views,admin,urls}.py`,
`apps/courses/templatetags/courses_extras.py`, `apps/courses/tests.py` (fixtures),
`apps/orders/{models,payment_processing,views,signals,admin}.py`, `apps/orders/tests.py`
(fixture + mock API), `templates/courses/{course_detail,lesson_player}.html`.

**Non touchés** (modifications préexistantes non commitées, à revoir séparément) : `accounts/*`,
`orders/forms.py`, templates accounts/orders/base, `README.md`, `.env.example`,
`orders/services.py` (supprimé avant ce chantier), `accounts.0003`, `orders.0008`, `core/validators.py`.

## 4. Modèles et migrations

Modèles ajoutés : `CourseRevision`, `CourseRevisionEvent`, `AccessGrant`, `PaymentRevisionLink`,
`PaymentReconciliation`. Champs ajoutés : `Course.published_revision`, `Enrollment.revision`,
`LessonProgress.revision`, `QuizAttempt.revision`, `QuizAttempt.attempt_snapshot`,
`Order.paid_at`, `OutboxEvent.lease_token`. Détail et ordre : `DATABASE_MIGRATION_PLAN.md`.

## 5. Tests exécutés

| Configuration | Résultat |
|---|---|
| PostgreSQL 17.6 local | 190 tests — **OK** |
| SQLite | 182 OK, 7 ignorés (PostgreSQL uniquement), 1 échec préexistant (`test_06`, passe sur PostgreSQL) |
| Migrations SQLite (copie de la base locale) | aller / retour / aller OK, données et progression identiques |
| Migrations PostgreSQL (`venus_luna_localtest`) | aller / retour / aller OK, triggers et contraintes présents puis retirés |
| Parcours HTTP sur données réelles migrées | catalogue, fiche, lecteur, tableau de bord, aperçu brouillon, pages admin : 200 ; workflow admin complet OK |

## 6. Problèmes non résolus / décisions restantes

1. **Contrat du webhook CashPay** : secret utilisé (`CASHPAY_SECRET_WEBHOOK` vs « clé API » de la
   doc) et claims exacts (`billed_amount`, `exp`, `jti`) à confirmer avec SEMOA. Pas de protection
   anti-rejeu par jeton (les rejeux sont sans effet grâce à l'idempotence).
2. **Worker non planifié en production** : le `Procfile` ne lance que `web`. Sans worker, le
   dispatch post-commit fonctionne, mais les reprises après échec (SMTP, PDF) ne se font pas.
3. **Base de code non commitée** : `payment_processing.py`, `orders.0008`, `accounts.0003` et
   d'autres modifications antérieures n'existent dans aucun commit.
4. **Médias** : les fichiers joints/vidéos ne sont référencés que par nom/URL dans les snapshots.
5. **Changements de comportement à valider métier** : trop-perçu refusé ; devise « CFA » refusée ;
   formation sans révision publiée invisible et non vendable ; suppression d'une leçon/quiz avec
   historique refusée ; republier une commande remboursée (statut « payé » via l'admin) ne
   réactive pas les droits révoqués (attribuer un accès manuel).
6. `xhtml2pdf` absent localement : la génération du reçu PDF n'a pas pu être testée de bout en bout.

## 7. À exécuter ultérieurement (manuel)

- Revue de code et commit (après commit séparé de la base préexistante).
- Répétition des migrations sur une copie restaurée de la production, puis déploiement (§5 du plan).
- Planification de `python manage.py process_outbox --once` (cron / tâche planifiée / worker).
- Permissions `review_courserevision` / `publish_courserevision` pour les relecteurs.
- Test sandbox CashPay (webhook + polling) avec les montants réels.
- Les bases locales créées pour les tests : `venus_luna_localtest` (PostgreSQL) peut être supprimée ;
  `db_local.sqlite3` n'a **pas** été migrée (lancer `migrate --settings=config.settings_local` pour l'utiliser).
