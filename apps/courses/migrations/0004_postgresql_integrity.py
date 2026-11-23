"""
Garanties d'intégrité au niveau de la base (PostgreSQL uniquement).

Django ne sait pas exprimer ces règles : elles sont posées en SQL. Sur SQLite (développement
et tests rapides), la migration est sans effet et les mêmes règles sont appliquées par le code
(CourseRevision.save/delete, services de workflow).

1. Clés étrangères composites « même formation » (cible : contrainte unique
   uniq_courserevision_course_id sur courses_courserevision(course_id, id)) :
   - courses_course(id, published_revision_id)            → révision de la même formation ;
   - courses_enrollment(course_id, revision_id)
   - courses_accessgrant(course_id, revision_id)
   - orders_paymentrevisionlink(course_id, course_revision_id)
   (MATCH SIMPLE : une valeur NULL n'est pas contrôlée, ce qui couvre l'historique non versionné.)
2. Trigger : Course.published_revision ne peut désigner qu'une révision APPROVED.
3. Trigger d'immuabilité des révisions (SUBMITTED figée, états terminaux immuables,
   published_at renseigné une seule fois, suppression limitée aux brouillons).
4. Trigger d'immuabilité des tentatives de quiz (résultat et contexte figés).
"""
from django.db import migrations

FORWARD_SQL = [
    # 1. Clés étrangères composites
    """ALTER TABLE courses_course ADD CONSTRAINT fk_course_published_revision_same_course
       FOREIGN KEY (id, published_revision_id) REFERENCES courses_courserevision (course_id, id)
       DEFERRABLE INITIALLY DEFERRED""",
    """ALTER TABLE courses_enrollment ADD CONSTRAINT fk_enrollment_revision_same_course
       FOREIGN KEY (course_id, revision_id) REFERENCES courses_courserevision (course_id, id)
       DEFERRABLE INITIALLY DEFERRED""",
    """ALTER TABLE courses_accessgrant ADD CONSTRAINT fk_accessgrant_revision_same_course
       FOREIGN KEY (course_id, revision_id) REFERENCES courses_courserevision (course_id, id)
       DEFERRABLE INITIALLY DEFERRED""",
    """ALTER TABLE orders_paymentrevisionlink ADD CONSTRAINT fk_paymentrevisionlink_revision_same_course
       FOREIGN KEY (course_id, course_revision_id) REFERENCES courses_courserevision (course_id, id)
       DEFERRABLE INITIALLY DEFERRED""",

    # 2. Révision publiée = révision APPROVED
    """CREATE OR REPLACE FUNCTION venus_course_published_revision_guard() RETURNS trigger AS $$
    BEGIN
        IF NEW.published_revision_id IS NOT NULL
           AND (TG_OP = 'INSERT' OR NEW.published_revision_id IS DISTINCT FROM OLD.published_revision_id) THEN
            IF NOT EXISTS (
                SELECT 1 FROM courses_courserevision r
                WHERE r.id = NEW.published_revision_id AND r.status = 'APPROVED'
            ) THEN
                RAISE EXCEPTION 'Course %: la révision publiée % doit être APPROVED', NEW.id, NEW.published_revision_id
                    USING ERRCODE = 'check_violation';
            END IF;
        END IF;
        RETURN NEW;
    END;
    $$ LANGUAGE plpgsql""",
    """CREATE TRIGGER trg_course_published_revision_guard
       BEFORE INSERT OR UPDATE OF published_revision_id ON courses_course
       FOR EACH ROW EXECUTE FUNCTION venus_course_published_revision_guard()""",

    # 3. Immuabilité des révisions
    """CREATE OR REPLACE FUNCTION venus_courserevision_guard() RETURNS trigger AS $$
    BEGIN
        IF TG_OP = 'DELETE' THEN
            IF OLD.status <> 'DRAFT' THEN
                RAISE EXCEPTION 'CourseRevision %: seule une révision DRAFT peut être supprimée', OLD.id
                    USING ERRCODE = 'integrity_constraint_violation';
            END IF;
            RETURN OLD;
        END IF;

        IF OLD.status = 'DRAFT' THEN
            IF NEW.status NOT IN ('DRAFT', 'SUBMITTED', 'WITHDRAWN') THEN
                RAISE EXCEPTION 'CourseRevision %: transition DRAFT -> % interdite', OLD.id, NEW.status
                    USING ERRCODE = 'integrity_constraint_violation';
            END IF;
            RETURN NEW;
        END IF;

        IF NEW.course_id IS DISTINCT FROM OLD.course_id
           OR NEW.revision_number IS DISTINCT FROM OLD.revision_number
           OR NEW.snapshot IS DISTINCT FROM OLD.snapshot
           OR NEW.content_hash IS DISTINCT FROM OLD.content_hash
           OR NEW.change_summary IS DISTINCT FROM OLD.change_summary
           OR NEW.created_by_id IS DISTINCT FROM OLD.created_by_id
           OR NEW.created_at IS DISTINCT FROM OLD.created_at
           OR NEW.submitted_at IS DISTINCT FROM OLD.submitted_at THEN
            RAISE EXCEPTION 'CourseRevision % (%) est figée', OLD.id, OLD.status
                USING ERRCODE = 'integrity_constraint_violation';
        END IF;

        IF OLD.status = 'SUBMITTED' THEN
            IF NEW.status NOT IN ('SUBMITTED', 'APPROVED', 'REJECTED', 'WITHDRAWN') THEN
                RAISE EXCEPTION 'CourseRevision %: transition SUBMITTED -> % interdite', OLD.id, NEW.status
                    USING ERRCODE = 'integrity_constraint_violation';
            END IF;
        ELSE
            IF NEW.status IS DISTINCT FROM OLD.status
               OR NEW.review_notes IS DISTINCT FROM OLD.review_notes
               OR NEW.reviewed_by_id IS DISTINCT FROM OLD.reviewed_by_id
               OR NEW.reviewed_at IS DISTINCT FROM OLD.reviewed_at
               OR NEW.approved_at IS DISTINCT FROM OLD.approved_at THEN
                RAISE EXCEPTION 'CourseRevision % (%) est immuable', OLD.id, OLD.status
                    USING ERRCODE = 'integrity_constraint_violation';
            END IF;
        END IF;

        IF OLD.published_at IS NOT NULL AND NEW.published_at IS DISTINCT FROM OLD.published_at THEN
            RAISE EXCEPTION 'CourseRevision %: published_at ne peut être renseigné qu''une fois', OLD.id
                USING ERRCODE = 'integrity_constraint_violation';
        END IF;
        RETURN NEW;
    END;
    $$ LANGUAGE plpgsql""",
    """CREATE TRIGGER trg_courserevision_guard
       BEFORE UPDATE OR DELETE ON courses_courserevision
       FOR EACH ROW EXECUTE FUNCTION venus_courserevision_guard()""",

    # 4. Immuabilité des tentatives de quiz
    """CREATE OR REPLACE FUNCTION venus_quizattempt_guard() RETURNS trigger AS $$
    BEGIN
        IF NEW.enrollment_id IS DISTINCT FROM OLD.enrollment_id
           OR NEW.quiz_id IS DISTINCT FROM OLD.quiz_id
           OR NEW.score IS DISTINCT FROM OLD.score
           OR NEW.passed IS DISTINCT FROM OLD.passed
           OR NEW.attempt_number IS DISTINCT FROM OLD.attempt_number
           OR NEW.submitted_at IS DISTINCT FROM OLD.submitted_at
           OR NEW.revision_id IS DISTINCT FROM OLD.revision_id
           OR NEW.attempt_snapshot IS DISTINCT FROM OLD.attempt_snapshot THEN
            RAISE EXCEPTION 'QuizAttempt %: une tentative soumise est immuable', OLD.id
                USING ERRCODE = 'integrity_constraint_violation';
        END IF;
        RETURN NEW;
    END;
    $$ LANGUAGE plpgsql""",
    """CREATE TRIGGER trg_quizattempt_guard
       BEFORE UPDATE ON courses_quizattempt
       FOR EACH ROW EXECUTE FUNCTION venus_quizattempt_guard()""",
]

BACKWARD_SQL = [
    "DROP TRIGGER IF EXISTS trg_quizattempt_guard ON courses_quizattempt",
    "DROP FUNCTION IF EXISTS venus_quizattempt_guard()",
    "DROP TRIGGER IF EXISTS trg_courserevision_guard ON courses_courserevision",
    "DROP FUNCTION IF EXISTS venus_courserevision_guard()",
    "DROP TRIGGER IF EXISTS trg_course_published_revision_guard ON courses_course",
    "DROP FUNCTION IF EXISTS venus_course_published_revision_guard()",
    "ALTER TABLE orders_paymentrevisionlink DROP CONSTRAINT IF EXISTS fk_paymentrevisionlink_revision_same_course",
    "ALTER TABLE courses_accessgrant DROP CONSTRAINT IF EXISTS fk_accessgrant_revision_same_course",
    "ALTER TABLE courses_enrollment DROP CONSTRAINT IF EXISTS fk_enrollment_revision_same_course",
    "ALTER TABLE courses_course DROP CONSTRAINT IF EXISTS fk_course_published_revision_same_course",
]


def _run(statements):
    def operation(apps, schema_editor):
        if schema_editor.connection.vendor != "postgresql":
            return
        for statement in statements:
            # params=None : pas d'interpolation (les RAISE EXCEPTION utilisent « % »).
            schema_editor.execute(statement, params=None)
    return operation


class Migration(migrations.Migration):

    dependencies = [
        ("courses", "0003_initial_revisions_from_existing_content"),
        ("orders", "0010_paid_at_revision_links_reconciliation"),
    ]

    operations = [
        migrations.RunPython(_run(FORWARD_SQL), _run(BACKWARD_SQL)),
    ]
