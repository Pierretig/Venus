# Stratégie de tests

## 1. Configurations

| Commande | Base | Usage |
|---|---|---|
| `python manage.py test --settings=config.settings_test` | SQLite en mémoire | boucle rapide ; tests PostgreSQL ignorés (skip) |
| `python manage.py test --settings=config.settings_pg_test` | PostgreSQL **local** (`test_venus_luna_localtest`) | référence : verrous, triggers, FK composites, concurrence |

`settings_pg_test` refuse tout hôte non local et ignore `DB_*`/`DATABASE_URL` du `.env`
(qui visent une base distante). Variables : `PG_TEST_NAME/USER/PASSWORD/HOST/PORT`.
**Ne jamais lancer `manage.py` sans `--settings`** : `config.settings` lit le `.env` distant.

Une simulation SQLite ne prouve rien sur les verrous PostgreSQL : les tests de concurrence
sont marqués `postgres_only` et n'ont de valeur que sur PostgreSQL.

## 2. Couverture des scénarios exigés

| Domaine | Scénario | Test |
|---|---|---|
| Versionnement | Création d'une révision | `RevisionWorkflowTests.test_create_draft_revision` |
| Versionnement | Modification interdite d'une révision approuvée | `test_approved_revision_cannot_be_modified` ; PG : `PostgresIntegrityTests.test_trigger_blocks_raw_update_of_approved_revision` |
| Validation | Rejet d'une révision soumise | `test_reject_submitted_revision_requires_reason` |
| Publication | Publication explicite | `test_explicit_publication`, `test_draft_or_submitted_cannot_be_published` |
| Publication | Conservation de l'ancienne révision | `test_previous_revision_kept_for_its_learners` |
| Paiement | Confirmation normale | `PaymentConfirmationTests.test_normal_confirmation`, `WebhookAndReconciliationTests.test_webhook_paid_exact_amount` |
| Paiement | Notification répétée | `test_repeated_notification_keeps_paid_at`, `CashPayAtomicPaymentTests.test_03_repeated_webhook` |
| Paiement | Double confirmation concurrente (PG) | `PostgresConcurrencyTests.test_double_concurrent_confirmation`, `CashPayAtomicPaymentTests.test_06_concurrent_confirmations` |
| Paiement | Mauvais montant | `test_wrong_amount_rejected_and_nothing_persisted`, `test_webhook_amount_verified_with_api_when_ambiguous` |
| Paiement | Mauvaise devise | `test_wrong_currency_rejected`, `test_webhook_wrong_currency_records_reconciliation` |
| Paiement | Référence dupliquée | `test_duplicate_reference_rejected`, `test_14_reference_already_used_by_another_order` |
| Paiement | Externe accepté, interne échoué | `test_external_paid_but_internal_confirmation_failed`, `test_paid_on_cancelled_order_records_reconciliation` |
| Capture | Plusieurs formations | `test_multiple_courses_each_line_has_own_revision` |
| Capture | Formation sans révision publiée | `test_course_without_published_revision`, `test_course_without_published_revision_not_sellable` |
| Capture | Publication concurrente au paiement (PG) | `PostgresConcurrencyTests.test_publication_concurrent_with_payment` |
| Outbox | Création atomique avec le paiement | `test_outbox_atomic_with_payment` |
| Outbox | Retry | `OutboxWorkerTests.test_retry_after_temporary_error`, `test_max_attempts_then_failed` |
| Outbox | Lease expirée | `test_expired_lease_is_reclaimed_and_old_worker_cannot_finish` |
| Outbox | Deux workers concurrents (PG) | `PostgresConcurrencyTests.test_two_workers_never_claim_same_event` |
| Accès | Droit unique | `AccessAndHistoryTests.test_single_access_grant_per_order_item` |
| Accès | Réachat | `test_repurchase_creates_new_grant_and_keeps_old` |
| Accès | Révocation après remboursement | `test_refund_revokes_access_and_keeps_history` |
| Historique | Consultation d'une ancienne tentative | `test_old_attempt_detail_view` |
| Historique | Changement des bonnes réponses | `test_old_attempt_survives_new_correct_answers` |
| Migration | Conservation des anciennes inscriptions | `DataMigrationTests`, `test_legacy_enrollment_is_not_versioned` |
| Migration | Aucun rattachement historique inventé | `DataMigrationTests.test_initial_revision_without_inventing_history` |

Autres : `test_learner_never_sees_working_copy`, `test_submit_freezes_snapshot`,
`test_instructor_cannot_approve`, `test_admin_marks_paid_captures_revision`,
`test_polling_without_billed_amount_does_not_confirm`, intégrité PG (même formation, APPROVED, tentative immuable).

Fichiers : `apps/courses/tests_versioning.py`, `apps/orders/tests_payment_capture.py`.
Fixture : `apps/courses/testing.py::publish_working_copy` (passe par le workflow réel).

## 3. Non-régression

Les 144 tests existants (boutique, panier, commandes, CashPay, comptes, avis, sous-domaines,
LMS) sont conservés. Adaptations (aucune suppression ni désactivation) :
- fixtures LMS et `CashPayAtomicPaymentTests` : publication d'une révision (une formation
  sans révision publiée n'est plus accessible ni vendable — décision R3) ;
- `test_status_endpoint_fallback_api_confirms_paid` : la réponse API simulée inclut désormais
  `billed_amount`/`amount`/`currency` conformément à la documentation CashPay V3.1.

## 4. Résultats (2026-11-23)

| Configuration | Résultat |
|---|---|
| PostgreSQL 17.6 local | **190 tests, OK** |
| SQLite | 190 tests : 182 OK, 7 ignorés (PostgreSQL uniquement), 1 échec **préexistant** : `test_06_concurrent_confirmations` (test de concurrence écrit pour PostgreSQL ; échouait déjà avant ce chantier sur SQLite ; passe sur PostgreSQL) |

## 5. Non couvert par des tests automatisés

- Rendu visuel des templates (contrôlé manuellement par requêtes HTTP : pages 200).
- Intégration réelle CashPay (sandbox) : non exécutée.
- Envoi réel d'emails et génération PDF (xhtml2pdf absent de l'environnement local).
- Charge / performance.
