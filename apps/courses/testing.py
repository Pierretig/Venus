"""
Aides de test (fixtures) pour le versionnement.

``publish_working_copy`` fige la copie de travail d'une formation dans une révision APPROVED
et la publie, en passant par le workflow réel (brouillon → soumission → approbation →
publication) avec un relecteur superutilisateur dédié. Pour une formation sans leçon (que le
workflow refuse de soumettre), la révision est créée directement à l'état APPROVED, comme le
fait la migration de reprise 0003.
"""
from django.contrib.auth import get_user_model
from django.utils import timezone

from .content import build_snapshot, snapshot_hash
from .models import CourseRevision
from . import revisions as wf


def _reviewer():
    User = get_user_model()
    user, created = User.objects.get_or_create(
        username="revision_reviewer_test",
        defaults={"email": "reviewer@test.invalid", "is_staff": True, "is_superuser": True},
    )
    if created:
        user.set_unusable_password()
        user.save()
    return user


def publish_working_copy(course, change_summary="Fixture de test"):
    reviewer = _reviewer()
    snapshot = build_snapshot(course)
    if any(module["lessons"] for module in snapshot["modules"]):
        revision = wf.create_draft_revision(course, reviewer, change_summary)
        revision = wf.submit_revision(revision, reviewer)
        revision = wf.approve_revision(revision, reviewer)
    else:
        now = timezone.now()
        number = (course.revisions.order_by("-revision_number").values_list("revision_number", flat=True).first() or 0) + 1
        revision = CourseRevision.objects.create(
            course=course, revision_number=number, status=CourseRevision.Status.APPROVED,
            snapshot=snapshot, content_hash=snapshot_hash(snapshot), change_summary=change_summary,
            submitted_at=now, reviewed_at=now, approved_at=now, reviewed_by=reviewer,
        )
    revision = wf.publish_revision(revision, reviewer)
    course.refresh_from_db()
    return revision
