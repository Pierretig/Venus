# Architecture LMS — Venus Luna (référence)

> Document de référence, aligné sur le code livré le 2026-11-23. Il remplace
> `docs/ARCHITECTURE_V19.md` et `docs/V19_FINAL_AUDIT.md` (contenus partiellement erronés).

## 1. Principes

| # | Principe | Mise en œuvre |
|---|----------|---------------|
| 1 | Identité permanente de la formation | `Course` (slug, prix, formateur, statut commercial) |
| 2 | Modification pédagogique ⇒ nouvelle révision | `CourseRevision` (workflow DRAFT → SUBMITTED → APPROVED/REJECTED) |
| 3 | Révision approuvée immuable | `CourseRevision.save/delete` + trigger PostgreSQL `trg_courserevision_guard` |
| 4 | Seule la révision publiée est la version courante | `Course.published_revision` (FK), modifié uniquement par `publish_revision()` |
| 5 | Chaque achat garde sa révision exacte | `orders.PaymentRevisionLink` (OneToOne `order_item`) |
| 6 | Paiement + capture + Outbox atomiques | `confirm_order_payment()` (une transaction) |
| 7 | Le worker ne choisit jamais la révision | La capture est faite dans la transaction de paiement ; le worker ne traite que reçu PDF et email |
| 8 | Droits persistants, traçables, idempotents | `AccessGrant` (un par ligne d'achat, révocation sans suppression) |
| 9 | Anciennes tentatives fidèlement consultables | `QuizAttempt.attempt_snapshot` + trigger d'immuabilité |
| 10 | Pas de régression | Données historiques conservées en `revision = NULL` ; 192 tests passent sur PostgreSQL |

## 2. Modèles

### 2.1 Application `courses`

- **Course** (existant) — ajout `published_revision` (FK `CourseRevision`, `PROTECT`, nullable, non éditable).
  `status` reste la visibilité commerciale ; une formation est visible/achetable si
  `status = published` **et** `published_revision` non nul (`Course.is_available_for_learners`).
- **CourseModule / Lesson / Quiz / QuizQuestion / QuizAnswerOption** (existants, inchangés) :
  **copie de travail** du formateur. Ils ne sont plus jamais servis directement aux apprenants.
- **CourseRevision** (nouveau) : `course`, `revision_number`, `status`, `snapshot` (JSON),
  `content_hash` (SHA-256), `change_summary`, `review_notes`, `created_by`, `reviewed_by`,
  `created_at`, `updated_at`, `submitted_at`, `reviewed_at`, `approved_at`, `published_at`.
  Contraintes : `uniq_courserevision_number (course, revision_number)`,
  `uniq_courserevision_course_id (course, id)` (cible des FK composites),
  `uniq_courserevision_open_per_course` (une seule révision DRAFT/SUBMITTED par formation),
  `chk_courserevision_snapshot_state`, `chk_courserevision_published_is_approved`.
- **CourseRevisionEvent** (nouveau) : journal append-only des actions (CREATED, SUBMITTED,
  APPROVED, REJECTED, WITHDRAWN, PUBLISHED, INITIAL_IMPORT) avec auteur, note et révision publiée remplacée.
- **AccessGrant** (nouveau) : `user`, `course`, `revision` (obligatoire), `enrollment`,
  `order_item` (OneToOne, achat uniquement), `source` (cashpay/free/manual_admin), `status`
  (active/revoked), `granted_at/by`, `revoked_at/by`, `revocation_reason`.
- **Enrollment** (existant) — ajout `revision` (révision suivie ; NULL = historique non versionné).
  Reste unique par (user, course) : c'est le dossier pédagogique (progression, tentatives, certificat).
- **LessonProgress** (existant) — ajout `revision` ; `lesson` passe en `on_delete=PROTECT`.
- **QuizAttempt** (existant) — ajout `revision` et `attempt_snapshot` ; `quiz` passe en `PROTECT`.
- **Certificate** (existant) : inchangé.

### 2.2 Application `orders`

Voir `PAYMENT_AND_OUTBOX.md` : `Order.paid_at`, `PaymentRevisionLink`, `PaymentReconciliation`,
`OutboxEvent.lease_token`.

## 3. Versionnement et snapshots (décision R1)

**Choix : snapshot JSON immuable par révision + tables relationnelles existantes comme espace de rédaction.**

| Critère | Snapshots relationnels (option A) | Snapshot JSON (option B, retenue) |
|---|---|---|
| Intégrité | FK internes, mais 5 tables dupliquées à figer (triggers sur chacune) | Un document, une empreinte SHA-256, un trigger |
| Performance | Jointures multiples par affichage | Une ligne lue, mise en cache par requête |
| Consultation | SQL direct | Via `CourseContent` (objets de vue) |
| Évolutivité | Migrations sur 5 tables | `schema_version` dans le document |
| Duplication | Duplique le modèle existant | Aucune table dupliquée |

Rôle de chaque stockage :
- Tables `CourseModule`/`Lesson`/`Quiz`… : copie de travail, éditée dans l'admin (inlines existants).
- `CourseRevision.snapshot` : contenu figé à la **soumission** (`build_snapshot`, `apps/courses/content.py`) :
  informations pédagogiques de la formation, modules et leçons publiés (ordre, textes, vidéo,
  référence de fichier joint, durée, aperçu gratuit), quiz, questions, types, options, bonnes
  réponses, points, score requis, nombre de tentatives.
- Les identifiants des objets vivants sont conservés dans le snapshot : ils servent d'identité
  stable pour les URL (`/lecon/<id>/`), `LessonProgress.lesson` et `QuizAttempt.quiz`.

Lecture : `CourseContent` (objets `ModuleView`, `LessonView`, `QuizView`… compatibles avec les
templates existants). Résolution (`services.resolve_content`) :
1. apprenant inscrit → révision de son inscription (historique : révision publiée courante, non enregistrée) ;
2. formateur/staff avec `?apercu=brouillon` → copie de travail (bandeau « aperçu ») ;
3. sinon → révision publiée.

## 4. Workflow de validation (`apps/courses/revisions.py`)

| Étape | Fonction | Qui | Effet |
|---|---|---|---|
| Créer | `create_draft_revision` | formateur de la formation, staff avec `change_course`, superuser | révision DRAFT n+1 (verrou Course pour la numérotation) |
| Soumettre | `submit_revision` | idem | snapshot + empreinte figés, `submitted_at` ; refus si aucune leçon |
| Retirer | `withdraw_revision` | auteur ou relecteur | DRAFT/SUBMITTED → WITHDRAWN |
| Approuver | `approve_revision` | permission `courses.review_courserevision` | SUBMITTED → APPROVED (contrôle d'empreinte) |
| Rejeter | `reject_revision` | idem, motif obligatoire | SUBMITTED → REJECTED |
| Publier | `publish_revision` | permission `courses.publish_courserevision` | verrou Course, `published_revision ←` révision APPROVED, `published_at` (une fois) |

APPROVED ≠ publiée : une révision peut rester approuvée sans être publiée. L'ancienne révision
publiée reste intacte et continue d'être servie à ses apprenants. Aucun statut ARCHIVED.

Interfaces : **admin Jazzmin** (l'espace formateur existant) — action « Créer une révision
brouillon » sur les formations ; fiche révision avec boutons de workflow, page de confirmation
(motif de rejet obligatoire), comparaison avec la révision publiée, aperçu du contenu figé,
historique des actions. Les formateurs (groupe « Formateurs ») ne voient que leurs formations.

## 5. Intégrité en base (PostgreSQL, migration `courses.0004`)

`limit_choices_to` n'étant pas une contrainte SQL, l'intégrité est posée en base :
- FK composites `(course_id, revision_id) → courserevision(course_id, id)` sur `courses_course`,
  `courses_enrollment`, `courses_accessgrant`, `orders_paymentrevisionlink` : une révision
  d'une autre formation est refusée.
- `trg_course_published_revision_guard` : la révision publiée doit être APPROVED.
- `trg_courserevision_guard` : SUBMITTED figée ; APPROVED/REJECTED/WITHDRAWN immuables ;
  `published_at` renseigné une seule fois ; suppression limitée aux DRAFT.
- `trg_quizattempt_guard` : une tentative soumise est immuable.

Sur SQLite (dev/tests rapides) ces règles sont appliquées par le code uniquement.

## 6. Droits d'accès (décision R2, `apps/courses/access.py`)

- Achat : `grant_purchase_access(order_item, revision)` — appelé **dans** la transaction de
  paiement après capture ; idempotent (OneToOne). Réachat = nouveau droit, les anciens restent.
- Gratuit / manuel : `grant_non_purchase_access` — révision publiée lue sous verrou Course ;
  un seul droit actif par (apprenant, formation, source).
- Révocation : `revoke_order_access` (signal annulation/remboursement), `revoke_grant`
  (action admin) — statut REVOKED + date + motif ; l'inscription passe CANCELLED seulement
  s'il ne reste aucun droit actif. Révisions, progressions et tentatives intactes.
- Inscription réactivée par un nouveau droit : elle suit la révision de ce nouveau droit.
- Contrôle d'accès (`can_user_access_lesson`) : staff/formateur ; aperçu gratuit ; sinon
  inscription active **et** leçon présente dans la révision suivie.

| Cas | Politique |
|---|---|
| Plusieurs achats simultanés de la même formation | chaque ligne a son droit ; incident `DUPLICATE_PURCHASE` pour remboursement éventuel |
| Réachat après remboursement/expiration | nouveau droit, nouvelle révision publiée, inscription réactivée |
| Attribution manuelle | droit `manual_admin` (staff/formateur via les vues existantes) |
| Accès gratuit | droit `free` |
| Commande multi-formations | un lien de révision et un droit par ligne |

## 7. Historique pédagogique

- `QuizAttempt.attempt_snapshot` : questions présentées, options, sélection, bonnes réponses à
  la date de l'évaluation, points, règle `all_or_nothing_per_question_v1`, score, résultat.
  La notation se fait contre le quiz de la révision suivie, jamais contre la copie de travail.
- Vue apprenant `courses:quiz_attempt_detail` (`/formations/quiz/tentative/<id>/`).
  Les bonnes réponses, la correction par question et les explications ne sont transmises
  que si elles ne peuvent plus servir à repasser le quiz : quiz réussi, tentatives épuisées
  (jamais si illimitées), quiz absent de la révision suivie, ou staff. Sinon, seules les
  sélections de l'apprenant et le score global sont affichés.
- `LessonProgress.revision` : révision dans laquelle la leçon a été vue/terminée.
- Données antérieures : `revision = NULL`, `attempt_snapshot = NULL` → affichées comme
  « non versionnées » (score seul) ; jamais rattachées automatiquement.

## 8. Limites connues

- Fichiers joints et vidéos : le snapshot conserve la **référence** (nom de fichier, URL). Si le
  fichier est supprimé du stockage ou si la vidéo externe change, une ancienne révision en est affectée.
- Les textes commerciaux (titre, description) affichés restent ceux de `Course` (identité permanente) ;
  le snapshot en garde une copie pour l'historique.
- Supprimer une leçon/un quiz ayant des progressions/tentatives est désormais refusé (PROTECT) :
  dépublier (`is_published=False`) puis soumettre une nouvelle révision.
- Une formation ayant des révisions ne peut plus être supprimée (archivage à la place).
- Modifier une inscription à la main dans l'admin `Enrollment` ne crée pas d'`AccessGrant`.
