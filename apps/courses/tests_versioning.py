"""
Tests du versionnement des formations, des droits d'accès et de l'historique pédagogique.

Les tests marqués « PostgreSQL » vérifient les garanties posées en base (triggers, clés
étrangères composites) : ils sont ignorés sur SQLite et doivent être exécutés avec
``--settings=config.settings_pg_test``.
"""
import unittest
from decimal import Decimal

from django.contrib.auth.models import Permission, User
from django.db import IntegrityError, connection, transaction
from django.test import Client, TestCase, TransactionTestCase, override_settings
from django.urls import reverse

from apps.courses import revisions as wf
from apps.courses.access import AccessGrantError, revoke_order_access
from apps.courses.models import (
    AccessGrant, Course, CourseModule, CourseRevision, CourseRevisionEvent,
    CourseRevisionImmutableError, Enrollment, Lesson, LessonProgress, Quiz,
    QuizAnswerOption, QuizAttempt, QuizQuestion,
)
from apps.courses.services import (
    can_user_access_lesson, enroll_student_in_course, evaluate_quiz_submission,
    record_lesson_progress,
)
from apps.courses.testing import publish_working_copy

postgres_only = unittest.skipUnless(connection.vendor == 'postgresql', "Garantie PostgreSQL (triggers / FK composites)")


def build_course(title="Formation Test", price="15000", instructor=None, with_quiz=True):
    course = Course.objects.create(
        title=title, description="Description", price=Decimal(price), is_free=(price == "0"),
        status=Course.Status.PUBLISHED, instructor=instructor,
    )
    module = CourseModule.objects.create(course=course, title="Module 1", order=0)
    l1 = Lesson.objects.create(module=module, title="Leçon 1", lesson_type='text', content="Contenu v1", order=0, is_free_preview=True)
    l2 = Lesson.objects.create(module=module, title="Leçon 2", lesson_type='quiz', order=1)
    quiz = q = good = bad = None
    if with_quiz:
        quiz = Quiz.objects.create(lesson=l2, title="Quiz", passing_score=100)
        q = QuizQuestion.objects.create(quiz=quiz, question_text="Bonne réponse ?", question_type='single', points=1)
        good = QuizAnswerOption.objects.create(question=q, option_text="A", is_correct=True, order=0)
        bad = QuizAnswerOption.objects.create(question=q, option_text="B", is_correct=False, order=1)
    return course, module, l1, l2, quiz, q, good, bad


class RevisionWorkflowTests(TestCase):
    def setUp(self):
        self.instructor = User.objects.create_user("formateur", password="x")
        self.reviewer = User.objects.create_user("relecteur", password="x", is_staff=True)
        self.reviewer.user_permissions.add(
            Permission.objects.get(codename='review_courserevision'),
            Permission.objects.get(codename='publish_courserevision'),
        )
        self.reviewer = User.objects.get(pk=self.reviewer.pk)  # purge du cache de permissions
        self.course, self.module, self.l1, self.l2, *_ = build_course(instructor=self.instructor)

    def _approved(self):
        rev = wf.create_draft_revision(self.course, self.instructor, "v")
        rev = wf.submit_revision(rev, self.instructor)
        return wf.approve_revision(rev, self.reviewer)

    def test_create_draft_revision(self):
        rev = wf.create_draft_revision(self.course, self.instructor, "Première version")
        self.assertEqual(rev.revision_number, 1)
        self.assertEqual(rev.status, CourseRevision.Status.DRAFT)
        self.assertIsNone(rev.snapshot)
        with self.assertRaises(wf.RevisionWorkflowError):
            wf.create_draft_revision(self.course, self.instructor)  # une seule révision ouverte
        self.assertTrue(CourseRevisionEvent.objects.filter(revision=rev, action='CREATED').exists())

    def test_stranger_cannot_create_draft(self):
        stranger = User.objects.create_user("inconnu", password="x")
        with self.assertRaises(wf.RevisionWorkflowError):
            wf.create_draft_revision(self.course, stranger)

    def test_submit_freezes_snapshot(self):
        rev = wf.create_draft_revision(self.course, self.instructor)
        rev = wf.submit_revision(rev, self.instructor)
        self.assertEqual(rev.status, CourseRevision.Status.SUBMITTED)
        self.assertEqual(rev.snapshot['modules'][0]['lessons'][0]['content'], "Contenu v1")
        # Modification ultérieure de la copie de travail : le snapshot ne bouge pas.
        Lesson.objects.filter(pk=self.l1.pk).update(content="Contenu modifié")
        rev.refresh_from_db()
        self.assertEqual(rev.snapshot['modules'][0]['lessons'][0]['content'], "Contenu v1")

    def test_approved_revision_cannot_be_modified(self):
        rev = self._approved()
        rev.snapshot = {"modules": []}
        with self.assertRaises(CourseRevisionImmutableError):
            rev.save()
        rev.refresh_from_db()
        rev.status = CourseRevision.Status.DRAFT
        with self.assertRaises(CourseRevisionImmutableError):
            rev.save()
        with self.assertRaises(CourseRevisionImmutableError):
            rev.delete()

    def test_reject_submitted_revision_requires_reason(self):
        rev = wf.submit_revision(wf.create_draft_revision(self.course, self.instructor), self.instructor)
        with self.assertRaises(wf.RevisionWorkflowError):
            wf.reject_revision(rev, self.reviewer, "  ")
        rev = wf.reject_revision(rev, self.reviewer, "Vidéo manquante")
        self.assertEqual(rev.status, CourseRevision.Status.REJECTED)
        self.assertEqual(rev.review_notes, "Vidéo manquante")
        with self.assertRaises(wf.RevisionWorkflowError):
            wf.publish_revision(rev, self.reviewer)
        # Une nouvelle révision brouillon peut être créée après le rejet.
        self.assertEqual(wf.create_draft_revision(self.course, self.instructor).revision_number, 2)

    def test_instructor_cannot_approve(self):
        rev = wf.submit_revision(wf.create_draft_revision(self.course, self.instructor), self.instructor)
        with self.assertRaises(wf.RevisionWorkflowError):
            wf.approve_revision(rev, self.instructor)

    def test_explicit_publication(self):
        rev = self._approved()
        self.course.refresh_from_db()
        self.assertIsNone(self.course.published_revision_id)  # approuvée ≠ publiée
        with self.assertRaises(wf.RevisionWorkflowError):
            wf.publish_revision(rev, self.instructor)  # pas la permission
        wf.publish_revision(rev, self.reviewer)
        self.course.refresh_from_db()
        rev.refresh_from_db()
        self.assertEqual(self.course.published_revision_id, rev.pk)
        self.assertIsNotNone(rev.published_at)
        self.assertTrue(CourseRevisionEvent.objects.filter(revision=rev, action='PUBLISHED').exists())

    def test_draft_or_submitted_cannot_be_published(self):
        rev = wf.create_draft_revision(self.course, self.instructor)
        with self.assertRaises(wf.RevisionWorkflowError):
            wf.publish_revision(rev, self.reviewer)
        rev = wf.submit_revision(rev, self.instructor)
        with self.assertRaises(wf.RevisionWorkflowError):
            wf.publish_revision(rev, self.reviewer)

    def test_previous_revision_kept_for_its_learners(self):
        rev1 = publish_working_copy(self.course)
        alice = User.objects.create_user("alice", password="x")
        Enrollment.objects.create(user=alice, course=self.course, revision=rev1, source='manual_admin')

        Lesson.objects.filter(pk=self.l1.pk).update(content="Contenu v2")
        rev2 = publish_working_copy(self.course)
        rev1.refresh_from_db()
        self.assertEqual(rev1.status, CourseRevision.Status.APPROVED)
        self.assertEqual(rev1.snapshot['modules'][0]['lessons'][0]['content'], "Contenu v1")

        enrollment = Enrollment.objects.get(user=alice)
        self.assertEqual(enrollment.get_content().get_lesson(self.l1.pk).content, "Contenu v1")
        bob = User.objects.create_user("bob", password="x")
        new_enrollment, _ = enroll_student_in_course(bob, self.course, source='manual_admin')
        self.assertEqual(new_enrollment.revision_id, rev2.pk)
        self.assertEqual(new_enrollment.get_content().get_lesson(self.l1.pk).content, "Contenu v2")

    def test_learner_never_sees_working_copy(self):
        publish_working_copy(self.course)
        Lesson.objects.create(module=self.module, title="Leçon brouillon", order=5)
        alice = User.objects.create_user("alice", password="x")
        enroll_student_in_course(alice, self.course, source='manual_admin')
        client = Client()
        client.force_login(alice)
        draft = Lesson.objects.get(title="Leçon brouillon")
        response = client.get(reverse('courses:lesson_detail', args=[self.course.slug, draft.pk]))
        self.assertEqual(response.status_code, 404)
        response = client.get(reverse('courses:lesson_detail', args=[self.course.slug, self.l1.pk]))
        self.assertEqual(response.status_code, 200)

    def test_course_without_published_revision_not_sellable(self):
        buyer = User.objects.create_user("buyer", password="x")
        client = Client()
        client.force_login(buyer)
        response = client.get(reverse('courses:buy_course', args=[self.course.slug]))
        self.assertRedirects(response, reverse('courses:course_detail', args=[self.course.slug]),
                             fetch_redirect_response=False)
        from apps.orders.models import Order
        self.assertFalse(Order.objects.exists())
        with self.assertRaises(AccessGrantError):
            enroll_student_in_course(buyer, self.course, source='manual_admin')
        self.assertNotIn(self.course, Course.objects.filter(published_revision__isnull=False))


class AccessAndHistoryTests(TestCase):
    def setUp(self):
        self.course, self.module, self.l1, self.l2, self.quiz, self.q, self.good, self.bad = build_course()
        self.rev1 = publish_working_copy(self.course)
        self.alice = User.objects.create_user("alice", email="alice@test.invalid", password="x")

    def _paid_order(self, user):
        from apps.orders.models import Order, OrderItem
        from apps.orders.payment_processing import confirm_order_payment
        order = Order.objects.create(user=user, email=user.email, total=Decimal("15000"), subtotal=Decimal("15000"))
        OrderItem.objects.create(order=order, course=self.course, name="F", price=Decimal("15000"), quantity=1)
        confirm_order_payment(order.id, amount_received="15000", currency="XOF")
        order.refresh_from_db()
        return order

    def test_single_access_grant_per_order_item(self):
        from apps.orders.payment_processing import capture_course_revisions
        order = self._paid_order(self.alice)
        self.assertEqual(AccessGrant.objects.filter(user=self.alice).count(), 1)
        with transaction.atomic():
            capture_course_revisions(order, source='admin_fulfillment')  # rejouée : aucun doublon
        self.assertEqual(AccessGrant.objects.filter(user=self.alice).count(), 1)
        grant = AccessGrant.objects.get(user=self.alice)
        with self.assertRaises(IntegrityError), transaction.atomic():
            AccessGrant.objects.create(user=self.alice, course=self.course, revision=self.rev1,
                                       enrollment=grant.enrollment, order_item=grant.order_item, source='cashpay')

    def test_refund_revokes_access_and_keeps_history(self):
        order = self._paid_order(self.alice)
        enrollment = Enrollment.objects.get(user=self.alice)
        attempt = evaluate_quiz_submission(enrollment, self.quiz, {str(self.q.id): str(self.good.id)})
        order.status = 'refunded'
        order.save()
        grant = AccessGrant.objects.get(user=self.alice)
        self.assertEqual(grant.status, AccessGrant.Status.REVOKED)
        self.assertIsNotNone(grant.revoked_at)
        self.assertIn("rembours", grant.revocation_reason.lower())
        enrollment.refresh_from_db()
        self.assertEqual(enrollment.status, Enrollment.Status.CANCELLED)
        self.assertTrue(QuizAttempt.objects.filter(pk=attempt.pk, revision=self.rev1).exists())
        self.assertEqual(CourseRevision.objects.get(pk=self.rev1.pk).status, CourseRevision.Status.APPROVED)
        self.assertFalse(can_user_access_lesson(self.alice, self.l2))

    def test_repurchase_creates_new_grant_and_keeps_old(self):
        first = self._paid_order(self.alice)
        first.status = 'refunded'
        first.save()
        Lesson.objects.filter(pk=self.l1.pk).update(content="Contenu v2")
        rev2 = publish_working_copy(self.course)
        second = self._paid_order(self.alice)
        grants = AccessGrant.objects.filter(user=self.alice).order_by('granted_at', 'pk')
        self.assertEqual(grants.count(), 2)
        self.assertEqual(grants[0].status, AccessGrant.Status.REVOKED)
        self.assertEqual(grants[0].order_item.order_id, first.pk)
        self.assertEqual(grants[0].revision_id, self.rev1.pk)
        self.assertEqual(grants[1].status, AccessGrant.Status.ACTIVE)
        self.assertEqual(grants[1].order_item.order_id, second.pk)
        self.assertEqual(grants[1].revision_id, rev2.pk)
        enrollment = Enrollment.objects.get(user=self.alice)
        self.assertEqual(enrollment.status, Enrollment.Status.ACTIVE)
        self.assertEqual(enrollment.revision_id, rev2.pk)

    def test_old_attempt_survives_new_correct_answers(self):
        self._paid_order(self.alice)
        enrollment = Enrollment.objects.get(user=self.alice)
        attempt = evaluate_quiz_submission(enrollment, self.quiz, {str(self.q.id): str(self.good.id)})
        self.assertTrue(attempt.passed)

        # Nouvelle révision : la bonne réponse change.
        QuizAnswerOption.objects.filter(pk=self.good.pk).update(is_correct=False)
        QuizAnswerOption.objects.filter(pk=self.bad.pk).update(is_correct=True)
        rev2 = publish_working_copy(self.course)

        attempt.refresh_from_db()
        self.assertTrue(attempt.passed)
        self.assertEqual(attempt.score, Decimal("100.00"))
        self.assertEqual(attempt.attempt_snapshot['questions'][0]['correct_option_ids'], [self.good.pk])
        self.assertEqual(attempt.revision_id, self.rev1.pk)

        # L'apprenant reste évalué sur SA révision (rev1), pas sur la nouvelle.
        again = evaluate_quiz_submission(enrollment, self.quiz, {str(self.q.id): str(self.good.id)})
        self.assertTrue(again.passed)
        # Un nouvel apprenant est évalué sur la révision publiée (rev2).
        bob = User.objects.create_user("bob", email="bob@test.invalid", password="x")
        self._paid_order(bob)
        bob_enrollment = Enrollment.objects.get(user=bob)
        self.assertEqual(bob_enrollment.revision_id, rev2.pk)
        bob_attempt = evaluate_quiz_submission(bob_enrollment, self.quiz, {str(self.q.id): str(self.good.id)})
        self.assertFalse(bob_attempt.passed)

    def test_old_attempt_detail_view(self):
        self._paid_order(self.alice)
        enrollment = Enrollment.objects.get(user=self.alice)
        attempt = evaluate_quiz_submission(enrollment, self.quiz, {str(self.q.id): str(self.bad.id)})
        QuizAnswerOption.objects.filter(pk=self.good.pk).update(option_text="A modifiée")
        client = Client()
        client.force_login(self.alice)
        response = client.get(reverse('courses:quiz_attempt_detail', args=[attempt.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "(votre réponse)")
        self.assertContains(response, "(bonne réponse)")
        self.assertNotContains(response, "A modifiée")
        other = User.objects.create_user("intrus", password="x")
        client.force_login(other)
        self.assertEqual(client.get(reverse('courses:quiz_attempt_detail', args=[attempt.pk])).status_code, 404)

    def test_progress_records_revision(self):
        self._paid_order(self.alice)
        progress, _ = record_lesson_progress(self.alice, self.l1, is_completed=True)
        self.assertEqual(progress.revision_id, self.rev1.pk)

    def test_legacy_enrollment_is_not_versioned(self):
        legacy = Enrollment.objects.create(user=self.alice, course=self.course, source='cashpay')
        LessonProgress.objects.create(enrollment=legacy, lesson=self.l1, is_completed=True)
        self.assertIsNone(legacy.revision_id)
        self.assertTrue(legacy.is_unversioned_legacy)
        # Le contenu servi est la révision publiée courante, sans rattachement enregistré.
        self.assertEqual(legacy.get_content().revision.pk, self.rev1.pk)
        legacy.refresh_from_db()
        self.assertIsNone(legacy.revision_id)
        self.assertFalse(AccessGrant.objects.filter(enrollment=legacy).exists())


@postgres_only
class PostgresIntegrityTests(TestCase):
    def setUp(self):
        self.course, *_ = build_course()
        self.rev1 = publish_working_copy(self.course)
        self.other, *_ = build_course(title="Autre formation")
        self.other_rev = publish_working_copy(self.other)

    def test_trigger_blocks_raw_update_of_approved_revision(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            CourseRevision.objects.filter(pk=self.rev1.pk).update(snapshot={"modules": []})
        with self.assertRaises(IntegrityError), transaction.atomic():
            CourseRevision.objects.filter(pk=self.rev1.pk).update(status='DRAFT')
        with self.assertRaises(IntegrityError), transaction.atomic():
            CourseRevision.objects.filter(pk=self.rev1.pk).delete()

    def test_published_revision_must_belong_to_same_course(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            Course.objects.filter(pk=self.course.pk).update(published_revision=self.other_rev)
            connection.check_constraints()

    def test_published_revision_must_be_approved(self):
        draft = wf.create_draft_revision(self.course, User.objects.get(username="revision_reviewer_test"))
        with self.assertRaises(IntegrityError), transaction.atomic():
            Course.objects.filter(pk=self.course.pk).update(published_revision=draft)

    def test_quiz_attempt_is_immutable(self):
        user = User.objects.create_user("alice", password="x")
        enrollment, _ = enroll_student_in_course(user, self.course, source='manual_admin')
        quiz = Quiz.objects.get(lesson__module__course=self.course)
        attempt = evaluate_quiz_submission(enrollment, quiz, {})
        with self.assertRaises(IntegrityError), transaction.atomic():
            QuizAttempt.objects.filter(pk=attempt.pk).update(score=Decimal("100"))


class DataMigrationTests(TransactionTestCase):
    """Reprise des données : révision initiale pour l'existant, aucun historique inventé."""

    migrate_from = [('courses', '0002_revisions_and_access_grants')]
    migrate_to = [('courses', '0004_postgresql_integrity')]

    def test_initial_revision_without_inventing_history(self):
        from django.db.migrations.executor import MigrationExecutor
        executor = MigrationExecutor(connection)
        executor.migrate(self.migrate_from)
        old_apps = executor.loader.project_state(self.migrate_from).apps

        HUser = old_apps.get_model('auth', 'User')
        HCourse = old_apps.get_model('courses', 'Course')
        HModule = old_apps.get_model('courses', 'CourseModule')
        HLesson = old_apps.get_model('courses', 'Lesson')
        HEnrollment = old_apps.get_model('courses', 'Enrollment')
        HProgress = old_apps.get_model('courses', 'LessonProgress')
        HOrder = old_apps.get_model('orders', 'Order')

        user = HUser.objects.create(username="historique")
        published = HCourse.objects.create(title="Publiée", slug="publiee", description="d", status='published')
        draft = HCourse.objects.create(title="Brouillon", slug="brouillon", description="d", status='draft')
        module = HModule.objects.create(course=published, title="M", order=0)
        lesson = HLesson.objects.create(module=module, title="L", slug="l", order=0)
        order = HOrder.objects.create(user=user, status='paid', payment_status=True, total=15000)
        enrollment = HEnrollment.objects.create(user=user, course=published, source='cashpay', order=order)
        HProgress.objects.create(enrollment=enrollment, lesson=lesson, is_completed=True)

        executor = MigrationExecutor(connection)
        executor.loader.build_graph()
        executor.migrate(executor.loader.graph.leaf_nodes())

        course = Course.objects.get(pk=published.pk)
        self.assertIsNotNone(course.published_revision_id)
        rev = course.published_revision
        self.assertEqual(rev.revision_number, 1)
        self.assertEqual(rev.status, CourseRevision.Status.APPROVED)
        self.assertEqual(rev.snapshot['modules'][0]['lessons'][0]['id'], lesson.pk)
        self.assertTrue(CourseRevisionEvent.objects.filter(revision=rev, action='INITIAL_IMPORT').exists())
        self.assertIsNone(Course.objects.get(pk=draft.pk).published_revision_id)

        e = Enrollment.objects.get(pk=enrollment.pk)
        self.assertIsNone(e.revision_id)                      # pas de révision inventée
        self.assertEqual(e.order_id, order.pk)                # relation préservée
        self.assertIsNone(LessonProgress.objects.get(enrollment=e).revision_id)
        from apps.orders.models import Order, PaymentRevisionLink
        self.assertIsNone(Order.objects.get(pk=order.pk).paid_at)   # pas de date de paiement inventée
        self.assertFalse(PaymentRevisionLink.objects.exists())
        self.assertFalse(AccessGrant.objects.exists())
        # L'apprenant historique conserve son accès.
        self.assertTrue(can_user_access_lesson(User.objects.get(pk=user.pk), Lesson.objects.get(pk=lesson.pk)))
