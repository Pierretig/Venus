"""
Reprise des données existantes (décision R6).

Pour chaque formation déjà exposée (statut publié ou archivé, ou ayant au moins une
inscription), crée la révision n°1 APPROVED à partir du contenu en vigueur au moment de
la migration et la publie. Objectif : les FUTURS achats et inscriptions disposent d'une
révision exacte ; le parcours actuel des apprenants est préservé.

Ce que cette migration ne fait PAS (aucune donnée historique inventée) :
- les inscriptions existantes gardent revision = NULL (historique non versionné) ;
- les progressions et tentatives existantes gardent revision = NULL ;
- Order.paid_at n'est pas rétro-renseigné ;
- aucun PaymentRevisionLink ni AccessGrant n'est créé pour les achats passés.

Le constructeur de snapshot est figé ici (copie de apps.courses.content.build_snapshot,
schéma v1) pour que la migration reste reproductible même si le code évolue.
"""
import hashlib
import json
from decimal import Decimal

from django.db import migrations
from django.utils import timezone

SUMMARY = ("Révision initiale générée automatiquement lors de la mise en place du versionnement "
           "(contenu en vigueur à la date de migration).")


def _file_name(field_file):
    if not field_file:
        return ""
    return getattr(field_file, "name", "") or ""


def _snapshot(course, Quiz):
    modules = []
    for module in course.modules.filter(is_published=True).order_by("order", "created_at", "id"):
        lessons = []
        for lesson in module.lessons.filter(is_published=True).order_by("order", "created_at", "id"):
            quiz_obj = Quiz.objects.filter(lesson_id=lesson.id).first()
            quiz = None
            if quiz_obj is not None:
                questions = []
                for q in quiz_obj.questions.all().order_by("order", "id"):
                    questions.append({
                        "id": q.id, "question_text": q.question_text, "question_type": q.question_type,
                        "order": q.order, "points": q.points, "explanation": q.explanation,
                        "options": [
                            {"id": o.id, "option_text": o.option_text, "is_correct": bool(o.is_correct), "order": o.order}
                            for o in q.options.all().order_by("order", "id")
                        ],
                    })
                quiz = {
                    "id": quiz_obj.id, "title": quiz_obj.title, "description": quiz_obj.description,
                    "passing_score": quiz_obj.passing_score, "max_attempts": quiz_obj.max_attempts,
                    "questions": questions,
                }
            lessons.append({
                "id": lesson.id, "title": lesson.title, "slug": lesson.slug, "lesson_type": lesson.lesson_type,
                "description": lesson.description, "content": lesson.content, "video_url": lesson.video_url,
                "attachment_file": _file_name(lesson.attachment_file), "attachment_name": lesson.attachment_name,
                "duration_minutes": lesson.duration_minutes, "order": lesson.order,
                "is_free_preview": bool(lesson.is_free_preview), "quiz": quiz,
            })
        modules.append({
            "id": module.id, "title": module.title, "description": module.description,
            "order": module.order, "lessons": lessons,
        })
    return {
        "schema_version": 1,
        "course": {
            "id": course.id, "title": course.title, "short_description": course.short_description,
            "description": course.description, "objectives": course.objectives,
            "prerequisites": course.prerequisites, "syllabus": course.syllabus, "level": course.level,
            "estimated_duration_hours": str(Decimal(course.estimated_duration_hours)),
            "certificate_enabled": bool(course.certificate_enabled),
            "certificate_passing_score": course.certificate_passing_score,
        },
        "modules": modules,
    }


def _hash(snapshot):
    canonical = json.dumps(snapshot, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def forwards(apps, schema_editor):
    Course = apps.get_model("courses", "Course")
    CourseRevision = apps.get_model("courses", "CourseRevision")
    CourseRevisionEvent = apps.get_model("courses", "CourseRevisionEvent")
    Enrollment = apps.get_model("courses", "Enrollment")
    Quiz = apps.get_model("courses", "Quiz")

    enrolled_course_ids = set(Enrollment.objects.values_list("course_id", flat=True))
    now = timezone.now()
    for course in Course.objects.order_by("id"):
        if course.published_revision_id is not None or CourseRevision.objects.filter(course_id=course.id).exists():
            continue
        if course.status not in ("published", "archived") and course.id not in enrolled_course_ids:
            continue
        snapshot = _snapshot(course, Quiz)
        revision = CourseRevision.objects.create(
            course_id=course.id, revision_number=1, status="APPROVED",
            snapshot=snapshot, content_hash=_hash(snapshot), change_summary=SUMMARY,
            submitted_at=now, reviewed_at=now, approved_at=now, published_at=now,
        )
        Course.objects.filter(pk=course.pk).update(published_revision_id=revision.pk)
        CourseRevisionEvent.objects.create(revision_id=revision.pk, action="INITIAL_IMPORT", note=SUMMARY)


def backwards(apps, schema_editor):
    """
    Retour arrière possible uniquement si aucune donnée n'a été rattachée aux révisions
    importées (aucun achat capturé, droit, progression ou tentative versionnés).
    """
    Course = apps.get_model("courses", "Course")
    CourseRevision = apps.get_model("courses", "CourseRevision")
    CourseRevisionEvent = apps.get_model("courses", "CourseRevisionEvent")
    imported_ids = list(
        CourseRevisionEvent.objects.filter(action="INITIAL_IMPORT").values_list("revision_id", flat=True)
    )
    revisions = CourseRevision.objects.filter(pk__in=imported_ids)
    for rel in ("enrollments", "lesson_progresses", "quiz_attempts", "access_grants"):
        if revisions.filter(**{f"{rel}__isnull": False}).exists():
            raise RuntimeError(
                f"Retour arrière refusé : des données ({rel}) référencent les révisions importées."
            )
    PaymentRevisionLink = apps.get_model("orders", "PaymentRevisionLink")
    if PaymentRevisionLink.objects.filter(course_revision_id__in=imported_ids).exists():
        raise RuntimeError("Retour arrière refusé : des achats ont capturé les révisions importées.")
    if CourseRevision.objects.exclude(pk__in=imported_ids).exists():
        raise RuntimeError("Retour arrière refusé : des révisions créées après l'import existent.")
    Course.objects.filter(published_revision_id__in=imported_ids).update(published_revision_id=None)
    # Suppression SQL directe : l'absence de toute référence a été vérifiée ci-dessus (le
    # collecteur de l'ORM ne peut pas parcourir les modèles historiques d'autres applications).
    ids = list(imported_ids)
    if ids:
        placeholders = ", ".join(["%s"] * len(ids))
        with schema_editor.connection.cursor() as cursor:
            cursor.execute(f"DELETE FROM {CourseRevisionEvent._meta.db_table} WHERE revision_id IN ({placeholders})", ids)
            cursor.execute(f"DELETE FROM {CourseRevision._meta.db_table} WHERE id IN ({placeholders})", ids)


class Migration(migrations.Migration):

    dependencies = [
        ("courses", "0002_revisions_and_access_grants"),
        # Garantit qu'au retour arrière cette migration est annulée AVANT la suppression
        # de orders_paymentrevisionlink (contrôlée par backwards()).
        ("orders", "0010_paid_at_revision_links_reconciliation"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
