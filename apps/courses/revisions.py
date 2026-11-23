"""
Workflow de versionnement des formations.

Règles :
- Le formateur (ou le staff) crée un brouillon, puis le soumet : le snapshot est figé.
- Un relecteur (permission ``courses.review_courserevision``) approuve ou rejette.
- La publication (permission ``courses.publish_courserevision``) est une action
  distincte qui met à jour ``Course.published_revision`` sous verrou de la ligne Course.

Ordre de verrouillage (cf. docs/PAYMENT_AND_OUTBOX.md) :
- publication : Course (FOR UPDATE) uniquement — la révision approuvée est immuable ;
- transitions de statut : CourseRevision (FOR UPDATE) uniquement.
Aucune de ces fonctions ne verrouille Order ni Product : pas d'acquisition croisée
possible avec la confirmation de paiement (Order → Course → Product).
"""
from django.db import IntegrityError, transaction
from django.db.models import Max
from django.utils import timezone

from .content import build_snapshot, snapshot_hash
from .models import Course, CourseRevision, CourseRevisionEvent


class RevisionWorkflowError(Exception):
    """Transition de workflow refusée (état, droits ou contenu invalides)."""


# ---------------------------------------------------------------------------
# Droits
# ---------------------------------------------------------------------------

def can_author(user, course) -> bool:
    if not (user and user.is_authenticated and user.is_active):
        return False
    if user.is_superuser:
        return True
    if course.instructor_id == user.id:
        return True
    return user.is_staff and user.has_perm('courses.change_course')


def can_review(user) -> bool:
    return bool(user and user.is_authenticated and user.is_active and user.has_perm('courses.review_courserevision'))


def can_publish(user) -> bool:
    return bool(user and user.is_authenticated and user.is_active and user.has_perm('courses.publish_courserevision'))


def _log(revision, action, actor, note="", previous_published=None):
    CourseRevisionEvent.objects.create(
        revision=revision,
        action=action,
        actor=actor if (actor and actor.is_authenticated) else None,
        note=note,
        previous_published_revision=previous_published,
    )


def _lock_revision(revision_id):
    return CourseRevision.objects.select_for_update().select_related('course').get(pk=revision_id)


# ---------------------------------------------------------------------------
# Transitions
# ---------------------------------------------------------------------------

@transaction.atomic
def create_draft_revision(course, user, change_summary=""):
    """Crée la révision brouillon de la formation (une seule révision ouverte à la fois)."""
    if not can_author(user, course):
        raise RevisionWorkflowError("Vous n'êtes pas autorisé(e) à modifier cette formation.")
    # Le verrou Course sérialise la numérotation des révisions d'une même formation.
    locked_course = Course.objects.select_for_update().get(pk=course.pk)
    if locked_course.revisions.filter(status__in=CourseRevision.OPEN_STATUSES).exists():
        raise RevisionWorkflowError("Une révision brouillon ou soumise existe déjà pour cette formation.")
    next_number = (locked_course.revisions.aggregate(m=Max('revision_number'))['m'] or 0) + 1
    try:
        with transaction.atomic():
            revision = CourseRevision.objects.create(
                course=locked_course,
                revision_number=next_number,
                status=CourseRevision.Status.DRAFT,
                change_summary=change_summary,
                created_by=user if user.is_authenticated else None,
            )
    except IntegrityError as exc:
        raise RevisionWorkflowError("Une révision ouverte existe déjà pour cette formation.") from exc
    _log(revision, CourseRevisionEvent.Action.CREATED, user, change_summary)
    return revision


@transaction.atomic
def submit_revision(revision, user, change_summary=None):
    """Fige le contenu de travail dans le snapshot et soumet la révision à validation."""
    revision = _lock_revision(revision.pk)
    if revision.status != CourseRevision.Status.DRAFT:
        raise RevisionWorkflowError("Seule une révision brouillon peut être soumise.")
    if not can_author(user, revision.course):
        raise RevisionWorkflowError("Vous n'êtes pas autorisé(e) à soumettre cette révision.")
    snapshot = build_snapshot(revision.course)
    if not any(module['lessons'] for module in snapshot['modules']):
        raise RevisionWorkflowError("La révision ne contient aucune leçon publiée : soumission impossible.")
    revision.snapshot = snapshot
    revision.content_hash = snapshot_hash(snapshot)
    if change_summary is not None:
        revision.change_summary = change_summary
    revision.status = CourseRevision.Status.SUBMITTED
    revision.submitted_at = timezone.now()
    revision.save()
    _log(revision, CourseRevisionEvent.Action.SUBMITTED, user, revision.change_summary)
    return revision


@transaction.atomic
def withdraw_revision(revision, user, note=""):
    revision = _lock_revision(revision.pk)
    if revision.status not in CourseRevision.OPEN_STATUSES:
        raise RevisionWorkflowError("Seule une révision brouillon ou soumise peut être retirée.")
    if not (can_author(user, revision.course) or can_review(user)):
        raise RevisionWorkflowError("Vous n'êtes pas autorisé(e) à retirer cette révision.")
    revision.status = CourseRevision.Status.WITHDRAWN
    revision.save()
    _log(revision, CourseRevisionEvent.Action.WITHDRAWN, user, note)
    return revision


@transaction.atomic
def approve_revision(revision, user, note=""):
    revision = _lock_revision(revision.pk)
    if not can_review(user):
        raise RevisionWorkflowError("Permission de revue requise.")
    if revision.status != CourseRevision.Status.SUBMITTED:
        raise RevisionWorkflowError("Seule une révision soumise peut être approuvée.")
    if snapshot_hash(revision.snapshot) != revision.content_hash:
        raise RevisionWorkflowError("Empreinte du snapshot incohérente : révision corrompue.")
    now = timezone.now()
    revision.status = CourseRevision.Status.APPROVED
    revision.reviewed_by = user
    revision.reviewed_at = now
    revision.approved_at = now
    revision.review_notes = note
    revision.save()
    _log(revision, CourseRevisionEvent.Action.APPROVED, user, note)
    return revision


@transaction.atomic
def reject_revision(revision, user, reason):
    revision = _lock_revision(revision.pk)
    if not can_review(user):
        raise RevisionWorkflowError("Permission de revue requise.")
    if revision.status != CourseRevision.Status.SUBMITTED:
        raise RevisionWorkflowError("Seule une révision soumise peut être rejetée.")
    reason = (reason or "").strip()
    if not reason:
        raise RevisionWorkflowError("Un motif de rejet est obligatoire.")
    revision.status = CourseRevision.Status.REJECTED
    revision.reviewed_by = user
    revision.reviewed_at = timezone.now()
    revision.review_notes = reason
    revision.save()
    _log(revision, CourseRevisionEvent.Action.REJECTED, user, reason)
    return revision


@transaction.atomic
def publish_revision(revision, user, note=""):
    """
    Publication explicite : Course.published_revision ← révision APPROVED.
    L'ancienne révision publiée reste intacte et continue d'être servie aux
    apprenants qui y sont rattachés.
    """
    if not can_publish(user):
        raise RevisionWorkflowError("Permission de publication requise.")
    course = Course.objects.select_for_update().get(pk=revision.course_id)
    # Relecture après verrou : une révision APPROVED est immuable, aucun verrou nécessaire.
    revision = CourseRevision.objects.get(pk=revision.pk)
    if revision.course_id != course.pk:
        raise RevisionWorkflowError("La révision n'appartient pas à cette formation.")
    if revision.status != CourseRevision.Status.APPROVED:
        raise RevisionWorkflowError("Seule une révision approuvée peut être publiée.")
    if course.published_revision_id == revision.pk:
        raise RevisionWorkflowError("Cette révision est déjà la révision publiée.")
    previous_id = course.published_revision_id
    Course.objects.filter(pk=course.pk).update(published_revision=revision)
    if revision.published_at is None:
        CourseRevision.objects.filter(pk=revision.pk, published_at__isnull=True).update(published_at=timezone.now())
    previous = CourseRevision.objects.get(pk=previous_id) if previous_id else None
    _log(revision, CourseRevisionEvent.Action.PUBLISHED, user, note, previous_published=previous)
    revision.refresh_from_db()
    return revision
