"""
Snapshots pédagogiques et lecture du contenu versionné.

Rôle des deux stockages (décision R1) :
- Les tables vivantes ``CourseModule`` / ``Lesson`` / ``Quiz`` / ``QuizQuestion`` /
  ``QuizAnswerOption`` sont l'espace de rédaction (copie de travail du formateur).
- ``CourseRevision.snapshot`` est un document JSON immuable figé à la soumission :
  c'est l'unique source de contenu servie aux apprenants.

Ce module ne dépend que d'attributs et de managers reverse : il fonctionne avec les
modèles réels comme avec les modèles historiques des migrations.
"""
import hashlib
import json
from decimal import Decimal

from django.core.exceptions import ObjectDoesNotExist

SNAPSHOT_SCHEMA_VERSION = 1


# ---------------------------------------------------------------------------
# Construction du snapshot depuis les tables vivantes
# ---------------------------------------------------------------------------

def _file_name(field_file):
    if not field_file:
        return ""
    return getattr(field_file, "name", "") or ""


def _quiz_dict(quiz):
    questions = []
    for q in quiz.questions.all().order_by("order", "id"):
        options = [
            {
                "id": o.id,
                "option_text": o.option_text,
                "is_correct": bool(o.is_correct),
                "order": o.order,
            }
            for o in q.options.all().order_by("order", "id")
        ]
        questions.append({
            "id": q.id,
            "question_text": q.question_text,
            "question_type": q.question_type,
            "order": q.order,
            "points": q.points,
            "explanation": q.explanation,
            "options": options,
        })
    return {
        "id": quiz.id,
        "title": quiz.title,
        "description": quiz.description,
        "passing_score": quiz.passing_score,
        "max_attempts": quiz.max_attempts,
        "questions": questions,
    }


def build_snapshot(course):
    """
    Construit le graphe pédagogique complet (modules et leçons publiés) d'une formation
    à partir des tables vivantes. Le résultat est sérialisable en JSON.
    """
    modules = []
    for module in course.modules.filter(is_published=True).order_by("order", "created_at", "id"):
        lessons = []
        for lesson in module.lessons.filter(is_published=True).order_by("order", "created_at", "id"):
            quiz = None
            try:
                quiz_obj = lesson.quiz
            except ObjectDoesNotExist:
                quiz_obj = None
            if quiz_obj is not None:
                quiz = _quiz_dict(quiz_obj)
            lessons.append({
                "id": lesson.id,
                "title": lesson.title,
                "slug": lesson.slug,
                "lesson_type": lesson.lesson_type,
                "description": lesson.description,
                "content": lesson.content,
                "video_url": lesson.video_url,
                "attachment_file": _file_name(lesson.attachment_file),
                "attachment_name": lesson.attachment_name,
                "duration_minutes": lesson.duration_minutes,
                "order": lesson.order,
                "is_free_preview": bool(lesson.is_free_preview),
                "quiz": quiz,
            })
        modules.append({
            "id": module.id,
            "title": module.title,
            "description": module.description,
            "order": module.order,
            "lessons": lessons,
        })
    return {
        "schema_version": SNAPSHOT_SCHEMA_VERSION,
        "course": {
            "id": course.id,
            "title": course.title,
            "short_description": course.short_description,
            "description": course.description,
            "objectives": course.objectives,
            "prerequisites": course.prerequisites,
            "syllabus": course.syllabus,
            "level": course.level,
            "estimated_duration_hours": str(Decimal(course.estimated_duration_hours)),
            "certificate_enabled": bool(course.certificate_enabled),
            "certificate_passing_score": course.certificate_passing_score,
        },
        "modules": modules,
    }


def snapshot_hash(snapshot):
    """Empreinte SHA-256 canonique d'un snapshot (contrôle d'intégrité et comparaison)."""
    canonical = json.dumps(snapshot, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Objets de lecture (compatibles avec les templates existants)
# ---------------------------------------------------------------------------

class ItemList(list):
    """Liste se comportant comme un QuerySet minimal dans les templates (.all, .count)."""

    def all(self):
        return self

    @property
    def count(self):
        return len(self)


class AttachmentView:
    def __init__(self, name):
        self.name = name

    def __bool__(self):
        return bool(self.name)

    @property
    def url(self):
        from django.core.files.storage import default_storage
        return default_storage.url(self.name)


class OptionView:
    def __init__(self, data):
        self.id = data["id"]
        self.option_text = data["option_text"]
        self.is_correct = data["is_correct"]
        self.order = data.get("order", 0)


class QuestionView:
    def __init__(self, data):
        self.id = data["id"]
        self.question_text = data["question_text"]
        self.question_type = data["question_type"]
        self.order = data.get("order", 0)
        self.points = data["points"]
        self.explanation = data.get("explanation", "")
        self.options = ItemList(OptionView(o) for o in data.get("options", []))
        self.raw = data

    def correct_option_ids(self):
        return {o.id for o in self.options if o.is_correct}


class QuizView:
    def __init__(self, data, lesson):
        self.id = data["id"]
        self.title = data["title"]
        self.description = data.get("description", "")
        self.passing_score = data["passing_score"]
        self.max_attempts = data.get("max_attempts", 0)
        self.questions = ItemList(QuestionView(q) for q in data.get("questions", []))
        self.lesson = lesson
        self.raw = data

    @property
    def total_questions_count(self):
        return len(self.questions)


class LessonView:
    is_published = True

    def __init__(self, data, module, content):
        self.id = data["id"]
        self.title = data["title"]
        self.slug = data.get("slug", "")
        self.lesson_type = data["lesson_type"]
        self.description = data.get("description", "")
        self.content = data.get("content", "")
        self.video_url = data.get("video_url", "")
        self.attachment_file = AttachmentView(data.get("attachment_file", ""))
        self.attachment_name = data.get("attachment_name", "")
        self.duration_minutes = data.get("duration_minutes", 0)
        self.order = data.get("order", 0)
        self.is_free_preview = data.get("is_free_preview", False)
        self.module = module
        self._content = content
        self.quiz = QuizView(data["quiz"], self) if data.get("quiz") else None

    @property
    def course(self):
        return self._content.course

    def get_absolute_url(self):
        from django.urls import reverse
        return reverse("courses:lesson_detail", kwargs={
            "course_slug": self._content.course.slug,
            "lesson_id": self.id,
        })

    def get_previous_lesson(self):
        return self._content.previous_lesson(self.id)

    def get_next_lesson(self):
        return self._content.next_lesson(self.id)


class ModuleView:
    is_published = True

    def __init__(self, data, content):
        self.id = data["id"]
        self.title = data["title"]
        self.description = data.get("description", "")
        self.order = data.get("order", 0)
        self._content = content
        self.lessons = ItemList(LessonView(lesson, self, content) for lesson in data.get("lessons", []))

    @property
    def course(self):
        return self._content.course


class CourseContent:
    """
    Vue en lecture seule du contenu d'une formation pour une révision donnée
    (``revision`` = None lorsqu'il s'agit d'un aperçu de la copie de travail).
    """

    def __init__(self, course, snapshot, revision=None):
        self.course = course
        self.revision = revision
        self.snapshot = snapshot
        self.course_data = snapshot.get("course", {})
        self.modules = ItemList(ModuleView(m, self) for m in snapshot.get("modules", []))
        self._lessons = [lesson for module in self.modules for lesson in module.lessons]
        self._lesson_index = {lesson.id: i for i, lesson in enumerate(self._lessons)}

    @property
    def is_preview(self):
        return self.revision is None

    @property
    def lessons(self):
        return list(self._lessons)

    @property
    def lesson_ids(self):
        return set(self._lesson_index)

    @property
    def total_lessons(self):
        return len(self._lessons)

    @property
    def total_duration_minutes(self):
        return sum(lesson.duration_minutes or 0 for lesson in self._lessons)

    def get_lesson(self, lesson_id):
        idx = self._lesson_index.get(lesson_id)
        return self._lessons[idx] if idx is not None else None

    def get_quiz(self, quiz_id):
        for lesson in self._lessons:
            if lesson.quiz and lesson.quiz.id == quiz_id:
                return lesson.quiz
        return None

    def previous_lesson(self, lesson_id):
        idx = self._lesson_index.get(lesson_id)
        if idx is None or idx == 0:
            return None
        return self._lessons[idx - 1]

    def next_lesson(self, lesson_id):
        idx = self._lesson_index.get(lesson_id)
        if idx is None or idx + 1 >= len(self._lessons):
            return None
        return self._lessons[idx + 1]

    def first_lesson(self):
        return self._lessons[0] if self._lessons else None


# ---------------------------------------------------------------------------
# Comparaison de deux snapshots (aide à la revue administrative)
# ---------------------------------------------------------------------------

def _flatten(snapshot):
    entries = {}
    if not snapshot:
        return entries
    for module in snapshot.get("modules", []):
        mod_copy = {k: v for k, v in module.items() if k != "lessons"}
        entries[f"module:{module['id']}"] = (module["title"], mod_copy)
        for lesson in module.get("lessons", []):
            entries[f"lesson:{lesson['id']}"] = (lesson["title"], dict(lesson, module_id=module["id"]))
    entries["course"] = ("Informations pédagogiques", snapshot.get("course", {}))
    return entries


def diff_snapshots(old, new):
    """
    Retourne une liste de tuples (type_changement, libellé) décrivant les différences
    structurelles entre deux snapshots. ``old`` peut être None (première révision).
    """
    before, after = _flatten(old), _flatten(new)
    changes = []
    for key in after:
        if key not in before:
            changes.append(("ajout", f"{key.split(':')[0]} « {after[key][0]} »"))
        elif before[key][1] != after[key][1]:
            changes.append(("modification", f"{key.split(':')[0]} « {after[key][0]} »"))
    for key in before:
        if key not in after:
            changes.append(("suppression", f"{key.split(':')[0]} « {before[key][0]} »"))
    return changes
