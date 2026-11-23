# Plan de migration de la base de données

## 1. État initial (constaté le 2026-11-23)

- Production : PostgreSQL (version non vérifiable depuis le dépôt). Local : SQLite (`config.settings_local`)
  et PostgreSQL 17.6 local disponible.
- Migrations non appliquées en local avant ce chantier : `accounts.0003_profile_city`,
  `orders.0008_create_outboxevent` (fichiers non versionnés dans git).
- Dérive : index `idx_shippingzone_price` déclaré dans le modèle sans migration.

## 2. Ordre des migrations

| # | Migration | Contenu | Réversible |
|---|-----------|---------|------------|
| 1 | `orders.0009_shippingzone_price_index` | dérive préexistante (index) | oui |
| 2 | `courses.0002_revisions_and_access_grants` | tables `CourseRevision`, `CourseRevisionEvent`, `AccessGrant` ; colonnes nullables `Course.published_revision`, `Enrollment.revision`, `LessonProgress.revision`, `QuizAttempt.revision`, `QuizAttempt.attempt_snapshot` ; contraintes | oui |
| 3 | `orders.0010_paid_at_revision_links_reconciliation` | `Order.paid_at` (NULL), `OutboxEvent.lease_token`, tables `PaymentRevisionLink`, `PaymentReconciliation` | oui |
| 4 | `courses.0003_initial_revisions_from_existing_content` | données : révision n°1 APPROVED + publiée pour chaque formation publiée/archivée ou ayant des inscriptions | oui, si aucune donnée n'y est rattachée |
| 5 | `courses.0004_postgresql_integrity` | FK composites, triggers (sans effet sur SQLite) | oui |

Toutes les colonnes ajoutées aux tables existantes sont nullables (pas de réécriture de table,
pas de valeur inventée). Le SQL généré (`sqlmigrate`) ne contient aucun `DROP`/`DELETE`.
Les changements `on_delete` (`LessonProgress.lesson`, `QuizAttempt.quiz` → PROTECT) sont sans SQL.

## 3. Compatibilité historique

| Donnée existante | Après migration |
|---|---|
| Inscriptions | `revision = NULL` (non versionnées), `order` conservé, accès inchangé (contenu = révision publiée courante, non enregistré) |
| Progressions, tentatives | `revision = NULL`, `attempt_snapshot = NULL` ; progression identique (vérifiée sur la base locale : 5 inscriptions, mêmes pourcentages) |
| Commandes payées | `paid_at = NULL` (date inconnue, non inventée) ; aucun `PaymentRevisionLink` ni `AccessGrant` rétroactif |
| Formations publiées/archivées ou avec inscrits | révision n°1 APPROVED publiée = contenu à la date de migration (événement `INITIAL_IMPORT`) |
| Formations brouillon sans inscrit | aucune révision : passer par le workflow pour publier |

## 4. Vérifications effectuées

- `makemigrations --check` : aucune dérive restante.
- Copie de `db_local.sqlite3` (9 formations, 5 inscriptions, 10 progressions, 1 tentative, 4 commandes) :
  migration aller, contrôle des données, retour complet (`courses 0001`, `orders 0008`) sans
  perte, ré-application. L'original `db_local.sqlite3` n'a pas été migré.
- Base PostgreSQL locale dédiée `venus_luna_localtest` : migration complète, présence des
  contraintes et triggers, retour arrière (triggers et fonctions supprimés), ré-application.
- Test automatisé `DataMigrationTests` (SQLite et PostgreSQL) : données créées à l'état
  antérieur via les modèles historiques, migration, assertions « aucun historique inventé ».

## 5. Procédure de déploiement (à exécuter manuellement — non faite)

1. Sauvegarde complète de la base de production (`pg_dump -Fc`).
2. Répétition sur une copie restaurée de la production (environnement de préproduction) :
   `python manage.py migrate --plan` puis `migrate`, puis contrôles §6.
3. Vérifier qu'aucune commande n'est en cours de paiement pendant la fenêtre (les tables
   `courses_*` reçoivent des `ALTER TABLE … ADD COLUMN` nullables : verrous brefs).
4. Déployer le code et appliquer les migrations (l'`entrypoint.sh` lance `migrate`).
5. Planifier le worker `process_outbox` (voir `PAYMENT_AND_OUTBOX.md`).
6. Attribuer les permissions `review_courserevision` / `publish_courserevision` aux relecteurs.

## 6. Contrôles post-migration

```sql
SELECT count(*) FROM courses_course WHERE status IN ('published','archived') AND published_revision_id IS NULL;  -- attendu 0
SELECT count(*) FROM courses_enrollment WHERE revision_id IS NOT NULL;   -- attendu 0 juste après migration
SELECT count(*) FROM orders_order WHERE paid_at IS NOT NULL;             -- attendu 0 juste après migration
SELECT tgname FROM pg_trigger WHERE tgname LIKE 'trg_%';                 -- 3 triggers
```

## 7. Retour arrière

1. Restaurer le code précédent **et** exécuter, avant :
   `python manage.py migrate courses 0001` puis `python manage.py migrate orders 0008`.
2. Le retour de `courses.0003` est refusé si des achats, droits, progressions ou tentatives
   référencent les révisions importées : dans ce cas, restaurer la sauvegarde plutôt que migrer à rebours.
3. Les données créées après le déploiement (révisions, liens, droits, incidents) sont perdues au
   retour arrière : privilégier une correction en avant.
