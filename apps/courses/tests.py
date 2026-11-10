from decimal import Decimal
from django.test import TestCase, Client, override_settings
from django.urls import reverse
from django.contrib.auth.models import User, Group, AnonymousUser
from django.utils import timezone

from apps.orders.models import Order, OrderItem
from apps.courses.models import (
    CourseCategory, Course, CourseModule, Lesson,
    Enrollment, LessonProgress,
    Quiz, QuizQuestion, QuizAnswerOption, QuizAttempt,
    Certificate,
)
from apps.courses.services import (
    can_user_access_lesson,
    enroll_student_in_course,
    record_lesson_progress,
    evaluate_quiz_submission,
    issue_certificate_for_enrollment,
)


@override_settings(SECURE_SSL_REDIRECT=False)
class LMSTestCase(TestCase):
    """Suite de tests automatisés exhaustive pour la plateforme de formation en ligne (LMS)."""

    def setUp(self):
        self.client = Client()

        # Utilisateurs de test
        self.admin_user = User.objects.create_superuser(username="admin_venus", email="admin@venus-luna.com", password="adminpass123")
        self.instructor = User.objects.create_user(username="instructor_marie", email="marie@venus-luna.com", password="securepass123", first_name="Marie", last_name="Luna")
        self.student = User.objects.create_user(username="student_alice", email="alice@test.com", password="securepass123", first_name="Alice", last_name="Dubois")
        self.other_student = User.objects.create_user(username="student_bob", email="bob@test.com", password="securepass123")

        # Catégorie de test
        self.category = CourseCategory.objects.create(name="Lithothérapie Holistique", slug="lithotherapie-holistique")

        # Formation payante
        self.paid_course = Course.objects.create(
            title="Maîtrise des Cristaux et Énergies",
            slug="maitrise-des-cristaux",
            category=self.category,
            instructor=self.instructor,
            level=Course.Level.BEGINNER,
            price=Decimal("15000"),
            is_free=False,
            status=Course.Status.PUBLISHED,
            certificate_enabled=True,
            certificate_passing_score=80,
        )

        # Formation gratuite
        self.free_course = Course.objects.create(
            title="Introduction à la Méditation du Soir",
            slug="intro-meditation",
            category=self.category,
            instructor=self.instructor,
            level=Course.Level.ALL_LEVELS,
            price=Decimal("0"),
            is_free=True,
            status=Course.Status.PUBLISHED,
            certificate_enabled=True,
        )

        # Modules
        self.module_1 = CourseModule.objects.create(course=self.paid_course, title="Fondements et Chakras", order=0)
        self.module_2 = CourseModule.objects.create(course=self.paid_course, title="Pratique et Purifications", order=1)

        # Leçons module 1
        self.lesson_1 = Lesson.objects.create(
            module=self.module_1,
            title="Introduction aux 7 Cristaux Maîtres",
            lesson_type=Lesson.LessonType.VIDEO,
            duration_minutes=15,
            order=0,
            is_free_preview=True,  # Aperçu gratuit
            is_published=True,
        )
        self.lesson_2 = Lesson.objects.create(
            module=self.module_1,
            title="Résonance vibratoire et harmonisation",
            lesson_type=Lesson.LessonType.TEXT,
            duration_minutes=20,
            order=1,
            is_free_preview=False,  # Réservée aux inscrits
            is_published=True,
        )

        # Leçon module 2 avec Quiz
        self.lesson_3 = Lesson.objects.create(
            module=self.module_2,
            title="Évaluation finale du module",
            lesson_type=Lesson.LessonType.QUIZ,
            duration_minutes=10,
            order=0,
            is_published=True,
        )

        # Quiz
        self.quiz = Quiz.objects.create(
            lesson=self.lesson_3,
            title="Quiz de validation Lithothérapie",
            passing_score=80,
        )
        self.q1 = QuizQuestion.objects.create(
            quiz=self.quiz,
            question_text="Quel cristal est principalement lié au chakra du cœur ?",
            question_type=QuizQuestion.QuestionType.SINGLE,
            points=1,
            order=0,
        )
        self.opt_1_wrong = QuizAnswerOption.objects.create(question=self.q1, option_text="Obsidienne noire", is_correct=False, order=0)
        self.opt_1_correct = QuizAnswerOption.objects.create(question=self.q1, option_text="Quartz rose", is_correct=True, order=1)

    # 1. Création et publication d'une formation
    def test_course_creation_and_properties(self):
        self.assertEqual(self.paid_course.total_lessons_count, 3)
        self.assertEqual(self.paid_course.total_duration_minutes, 45)
        self.assertTrue(self.paid_course.slug.startswith("maitrise-des-cristaux"))

    # 2. Création et navigation ordonnée des leçons
    def test_lesson_navigation(self):
        next_l1 = self.lesson_1.get_next_lesson()
        self.assertEqual(next_l1.id, self.lesson_2.id)

        next_l2 = self.lesson_2.get_next_lesson()
        self.assertEqual(next_l2.id, self.lesson_3.id)

        prev_l3 = self.lesson_3.get_previous_lesson()
        self.assertEqual(prev_l3.id, self.lesson_2.id)

    # 3. Inscription gratuite
    def test_free_enrollment(self):
        self.client.login(username="student_alice", password="securepass123")
        url = reverse('courses:enroll_free', kwargs={'slug': self.free_course.slug})
        response = self.client.post(url)
        self.assertEqual(response.status_code, 302)

        enrollment = Enrollment.objects.filter(user=self.student, course=self.free_course).first()
        self.assertIsNotNone(enrollment)
        self.assertEqual(enrollment.status, Enrollment.Status.ACTIVE)
        self.assertEqual(enrollment.source, Enrollment.Source.FREE)

    # 4. Refus d'inscription directe gratuite sur formation payante
    def test_free_enrollment_rejected_on_paid_course(self):
        self.client.login(username="student_alice", password="securepass123")
        url = reverse('courses:enroll_free', kwargs={'slug': self.paid_course.slug})
        response = self.client.post(url)
        # Doit refuser et rediriger vers la page d'achat
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Enrollment.objects.filter(user=self.student, course=self.paid_course).exists())

    # 5. Contrôle des accès : Aperçu gratuit vs leçon protégée
    def test_lesson_access_control(self):
        anon = AnonymousUser()
        # Visiteur anonyme : peut voir l'aperçu gratuit (lesson_1)
        self.assertTrue(can_user_access_lesson(anon, self.lesson_1))
        # Visiteur anonyme : ne peut pas voir lesson_2
        self.assertFalse(can_user_access_lesson(anon, self.lesson_2))

        # Alice non inscrite : ne peut pas voir lesson_2
        self.assertFalse(can_user_access_lesson(self.student, self.lesson_2))

        # Inscription d'Alice à paid_course
        Enrollment.objects.create(user=self.student, course=self.paid_course, status=Enrollment.Status.ACTIVE)
        # Alice inscrite : a maintenant accès
        self.assertTrue(can_user_access_lesson(self.student, self.lesson_2))

    # 6. Achat CashPay & Automatisation de l'inscription via commande
    def test_order_payment_activates_course_enrollment(self):
        # Création d'une commande payée contenant la formation
        order = Order.objects.create(
            user=self.student,
            email=self.student.email,
            status='pending',
            payment_status=False,
            total=Decimal("15000"),
        )
        OrderItem.objects.create(
            order=order,
            course=self.paid_course,
            name=self.paid_course.title,
            price=self.paid_course.price,
            quantity=1,
        )

        # Aucune inscription active au départ
        self.assertFalse(Enrollment.objects.filter(user=self.student, course=self.paid_course).exists())

        # Simulation de la confirmation du paiement (CashPay webhook / return)
        order.status = 'paid'
        order.payment_status = True
        order.save()

        # Le signal post_save doit automatiquement débloquer l'inscription !
        enrollment = Enrollment.objects.filter(user=self.student, course=self.paid_course).first()
        self.assertIsNotNone(enrollment)
        self.assertEqual(enrollment.status, Enrollment.Status.ACTIVE)
        self.assertEqual(enrollment.source, Enrollment.Source.CASHPAY)
        self.assertEqual(enrollment.order_id, order.id)

    # 7. Idempotence : Paiement répété ne crée pas de doublon
    def test_payment_idempotence(self):
        order = Order.objects.create(user=self.student, email=self.student.email, status='paid', payment_status=True, total=15000)
        OrderItem.objects.create(order=order, course=self.paid_course, price=15000, quantity=1)
        order.save()

        # Première inscription
        self.assertEqual(Enrollment.objects.filter(user=self.student, course=self.paid_course).count(), 1)

        # Deuxième sauvegarde / rejeu du webhook
        order.save()
        self.assertEqual(Enrollment.objects.filter(user=self.student, course=self.paid_course).count(), 1)

    # 8. Annulation ou remboursement d'une commande désactive l'accès
    def test_cancelled_order_deactivates_enrollment(self):
        order = Order.objects.create(user=self.student, email=self.student.email, status='paid', payment_status=True, total=15000)
        OrderItem.objects.create(order=order, course=self.paid_course, price=15000, quantity=1)
        order.save()

        enrollment = Enrollment.objects.get(user=self.student, course=self.paid_course)
        self.assertEqual(enrollment.status, Enrollment.Status.ACTIVE)

        # Annulation
        order.status = 'cancelled'
        order.save()

        enrollment.refresh_from_db()
        self.assertEqual(enrollment.status, Enrollment.Status.CANCELLED)

    # 9. Suivi de progression et calcul du pourcentage
    def test_progress_tracking(self):
        enrollment = Enrollment.objects.create(user=self.student, course=self.paid_course, status=Enrollment.Status.ACTIVE)
        self.assertEqual(enrollment.get_progress_percentage(), 0)

        # Terminer la leçon 1
        record_lesson_progress(self.student, self.lesson_1, is_completed=True)
        enrollment.refresh_from_db()
        # 1 sur 3 leçons = 33%
        self.assertEqual(enrollment.get_progress_percentage(), 33)

        # Terminer la leçon 2
        record_lesson_progress(self.student, self.lesson_2, is_completed=True)
        enrollment.refresh_from_db()
        # 2 sur 3 leçons = 66%
        self.assertEqual(enrollment.get_progress_percentage(), 66)

    # 10. Évaluation de Quiz sécurisée (100% côté serveur)
    def test_quiz_evaluation(self):
        enrollment = Enrollment.objects.create(user=self.student, course=self.paid_course, status=Enrollment.Status.ACTIVE)

        # Mauvaise réponse
        bad_attempt = evaluate_quiz_submission(enrollment, self.quiz, {str(self.q1.id): str(self.opt_1_wrong.id)})
        self.assertFalse(bad_attempt.passed)
        self.assertEqual(bad_attempt.score, Decimal("0.00"))

        # Bonne réponse
        good_attempt = evaluate_quiz_submission(enrollment, self.quiz, {str(self.q1.id): str(self.opt_1_correct.id)})
        self.assertTrue(good_attempt.passed)
        self.assertEqual(good_attempt.score, Decimal("100.00"))

        # Vérifie que la leçon associée au quiz a été automatiquement marquée complétée
        progress = LessonProgress.objects.get(enrollment=enrollment, lesson=self.lesson_3)
        self.assertTrue(progress.is_completed)

    # 11. Génération de Certificat et fichier PDF
    def test_certificate_generation(self):
        enrollment = Enrollment.objects.create(user=self.student, course=self.paid_course, status=Enrollment.Status.ACTIVE)

        # Terminer toutes les leçons
        record_lesson_progress(self.student, self.lesson_1, is_completed=True)
        record_lesson_progress(self.student, self.lesson_2, is_completed=True)
        record_lesson_progress(self.student, self.lesson_3, is_completed=True)

        enrollment.refresh_from_db()
        self.assertEqual(enrollment.status, Enrollment.Status.COMPLETED)

        # Vérifie que le certificat a été délivré
        cert = Certificate.objects.filter(enrollment=enrollment).first()
        self.assertIsNotNone(cert)
        self.assertTrue(cert.certificate_code.startswith("VL-"))
        self.assertTrue(cert.is_valid)
        self.assertTrue(bool(cert.pdf_file))

    # 12. Vérification publique de certificat
    def test_verify_certificate_view(self):
        enrollment = Enrollment.objects.create(user=self.student, course=self.paid_course, status=Enrollment.Status.COMPLETED)
        cert = issue_certificate_for_enrollment(enrollment)

        # Code valide
        url_valid = reverse('courses:verify_certificate', kwargs={'code': cert.certificate_code})
        response = self.client.get(url_valid)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, cert.certificate_code)
        self.assertContains(response, "Certificat Authentique")
        # Ne divulgue pas l'email de l'étudiant
        self.assertNotContains(response, self.student.email)

        # Code invalide
        url_invalid = reverse('courses:verify_certificate', kwargs={'code': 'VL-FAKENUMBER'})
        response_invalid = self.client.get(url_invalid)
        self.assertEqual(response_invalid.status_code, 200)
        self.assertContains(response_invalid, "Certificat Introuvable")

    # 13. Tableau de bord apprenant
    def test_student_dashboard_view(self):
        self.client.login(username="student_alice", password="securepass123")
        Enrollment.objects.create(user=self.student, course=self.paid_course, status=Enrollment.Status.ACTIVE)

        url = reverse('courses:student_dashboard')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.paid_course.title)
        self.assertContains(response, "Mon Sanctuaire Pédagogique")

    # 14. Protection IDOR sur le téléchargement de certificat
    def test_certificate_download_idor_protection(self):
        enrollment = Enrollment.objects.create(user=self.student, course=self.paid_course, status=Enrollment.Status.COMPLETED)
        cert = issue_certificate_for_enrollment(enrollment)

        # Bob (autre utilisateur) tente de télécharger le certificat d'Alice
        self.client.login(username="student_bob", password="securepass123")
        url = reverse('courses:download_certificate', kwargs={'certificate_code': cert.certificate_code})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 404)

        # Alice (propriétaire) peut le télécharger
        self.client.login(username="student_alice", password="securepass123")
        response_alice = self.client.get(url)
        self.assertEqual(response_alice.status_code, 200)
        self.assertEqual(response_alice['Content-Type'], 'application/pdf')

