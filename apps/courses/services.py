import io
import logging
from decimal import Decimal
from typing import Tuple, Dict, Any, List

from django.conf import settings
from django.utils import timezone
from django.core.files.base import ContentFile
from django.urls import reverse

from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib import colors
from reportlab.pdfgen import canvas
from reportlab.graphics.shapes import Drawing
from reportlab.graphics.barcode import qr

from .models import (
    Course, Lesson, Enrollment, LessonProgress,
    Quiz, QuizAttempt, Certificate,
)

logger = logging.getLogger(__name__)


def can_user_access_lesson(user, lesson: Lesson) -> bool:
    """
    Contrôle d'accès strict à une leçon :
    - Aperçu gratuit (is_free_preview=True) : accessible à tous (y compris anonymes).
    - Administrateurs / Staff : accès total.
    - Formateur responsable du cours : accès total.
    - Apprenant : uniquement si authentifié avec inscription active (Enrollment.Status.ACTIVE ou COMPLETED).
    """
    if not lesson.is_published or not lesson.module.is_published:
        if not (user.is_authenticated and user.is_staff):
            return False

    if lesson.is_free_preview:
        return True

    if not user.is_authenticated:
        return False

    if user.is_staff or user.is_superuser:
        return True

    if lesson.module.course.instructor_id == user.id:
        return True

    return Enrollment.objects.filter(
        user=user,
        course=lesson.module.course,
        status__in=[Enrollment.Status.ACTIVE, Enrollment.Status.COMPLETED],
    ).exists()


def enroll_student_in_course(user, course: Course, source: str = 'free', order=None) -> Tuple[Enrollment, bool]:
    """
    Inscrit un apprenant à une formation de façon idempotente et sécurisée.
    Garantit qu'une formation payante ne peut être débloquée sans paiement ou décision admin.
    """
    if not user.is_authenticated:
        raise ValueError("L'utilisateur doit être connecté pour s'inscrire à une formation.")

    if not course.is_free and source == 'free' and not user.is_staff:
        raise PermissionError("Cette formation est payante et nécessite une commande validée.")

    enrollment, created = Enrollment.objects.get_or_create(
        user=user,
        course=course,
        defaults={
            'status': Enrollment.Status.ACTIVE,
            'source': source,
            'order': order,
            'last_activity_at': timezone.now(),
        }
    )

    if not created and enrollment.status != Enrollment.Status.ACTIVE:
        enrollment.status = Enrollment.Status.ACTIVE
        if order:
            enrollment.order = order
        enrollment.source = source
        enrollment.last_activity_at = timezone.now()
        enrollment.save(update_fields=['status', 'order', 'source', 'last_activity_at'])

    return enrollment, created


def record_lesson_progress(user, lesson: Lesson, is_completed: bool = False, position_seconds: int = 0) -> Tuple[LessonProgress, bool]:
    """
    Enregistre ou met à jour la progression d'un apprenant sur une leçon.
    Met à jour la dernière leçon consultée et vérifie l'éligibilité à la certification.
    """
    enrollment = Enrollment.objects.filter(
        user=user,
        course=lesson.module.course,
        status__in=[Enrollment.Status.ACTIVE, Enrollment.Status.COMPLETED],
    ).first()

    if not enrollment:
        raise PermissionError("L'utilisateur n'est pas inscrit à cette formation.")

    progress, created = LessonProgress.objects.get_or_create(
        enrollment=enrollment,
        lesson=lesson,
        defaults={
            'is_completed': is_completed,
            'completed_at': timezone.now() if is_completed else None,
            'last_position_seconds': position_seconds,
        }
    )

    update_fields = ['last_accessed_at']
    if position_seconds > 0:
        progress.last_position_seconds = position_seconds
        update_fields.append('last_position_seconds')

    if is_completed and not progress.is_completed:
        progress.is_completed = True
        progress.completed_at = timezone.now()
        update_fields.extend(['is_completed', 'completed_at'])

    progress.save(update_fields=update_fields)

    # Mise à jour de l'inscription
    enrollment.last_accessed_lesson = lesson
    enrollment.last_activity_at = timezone.now()
    enrollment.save(update_fields=['last_accessed_lesson', 'last_activity_at'])

    if is_completed:
        course_completed = enrollment.check_and_update_completion()
        if course_completed and enrollment.course.certificate_enabled:
            issue_certificate_for_enrollment(enrollment)

    return progress, created


def evaluate_quiz_submission(enrollment: Enrollment, quiz: Quiz, user_answers: Dict[str, Any]) -> QuizAttempt:
    """
    Évalue les réponses d'un apprenant à un quiz :
    - Validation 100% côté serveur (aucune bonne réponse transmise au frontend).
    - Calcul du pourcentage de réussite.
    - Enregistrement de la tentative.
    - Si réussi, marque automatiquement la leçon associée comme complétée.
    """
    questions = quiz.questions.prefetch_related('options').all()
    total_points = sum(q.points for q in questions)
    earned_points = 0

    for question in questions:
        q_id_str = str(question.id)
        submitted = user_answers.get(q_id_str)
        if not submitted:
            continue

        correct_option_ids = set(question.options.filter(is_correct=True).values_list('id', flat=True))

        if question.question_type == question.QuestionType.SINGLE:
            try:
                selected_id = int(submitted)
                if selected_id in correct_option_ids:
                    earned_points += question.points
            except (ValueError, TypeError):
                pass
        else:
            # Choix multiple
            try:
                selected_ids = set(int(x) for x in submitted if str(x).isdigit())
                if selected_ids == correct_option_ids and len(correct_option_ids) > 0:
                    earned_points += question.points
            except (ValueError, TypeError):
                pass

    score = Decimal("0.00")
    if total_points > 0:
        score = Decimal(str(round((earned_points / total_points) * 100, 2)))

    passed = (score >= quiz.passing_score)

    attempts_count = enrollment.quiz_attempts.filter(quiz=quiz).count()
    attempt = QuizAttempt.objects.create(
        enrollment=enrollment,
        quiz=quiz,
        score=score,
        passed=passed,
        attempt_number=attempts_count + 1,
    )

    if passed:
        record_lesson_progress(enrollment.user, quiz.lesson, is_completed=True)

    return attempt


def issue_certificate_for_enrollment(enrollment: Enrollment) -> Certificate:
    """
    Génère ou récupère le certificat d'un apprenant pour une formation terminée.
    Génère le document PDF vectoriel de haute qualité avec QR code de vérification.
    """
    certificate, created = Certificate.objects.get_or_create(
        enrollment=enrollment,
        defaults={
            'issued_at': timezone.now(),
            'is_valid': True,
        }
    )

    if not certificate.pdf_file or created:
        pdf_bytes = build_certificate_pdf_bytes(certificate)
        filename = f"certificat_{certificate.certificate_code}.pdf"
        certificate.pdf_file.save(filename, ContentFile(pdf_bytes), save=True)

    return certificate


def build_certificate_pdf_bytes(certificate: Certificate) -> bytes:
    """
    Construit le rendu PDF haute fidélité du certificat avec ReportLab :
    - Format A4 Paysage.
    - Cadre or et émeraude.
    - Typographie soignée, sceau Venus Luna et signature.
    - QR Code de vérification publique.
    """
    buffer = io.BytesIO()
    # Format A4 Paysage (842 x 595 pt)
    p = canvas.Canvas(buffer, pagesize=landscape(A4))
    width, height = landscape(A4)

    # Fond doux de prestige
    p.setFillColor(colors.HexColor("#fdfcf7"))
    p.rect(0, 0, width, height, fill=1, stroke=0)

    # Double bordure d'ornement (Émeraude & Or)
    p.setStrokeColor(colors.HexColor("#1c683b"))
    p.setLineWidth(5)
    p.rect(20, 20, width - 40, height - 40, fill=0, stroke=1)

    p.setStrokeColor(colors.HexColor("#d4af37"))
    p.setLineWidth(1.5)
    p.rect(28, 28, width - 56, height - 56, fill=0, stroke=1)

    # En-tête : Nom de l'Institut
    p.setFont("Helvetica-Bold", 14)
    p.setFillColor(colors.HexColor("#d4af37"))
    p.drawCentredString(width / 2, height - 65, "INSTITUT SPIRITUEL & BIEN-ÊTRE")

    p.setFont("Helvetica-Bold", 26)
    p.setFillColor(colors.HexColor("#1c683b"))
    p.drawCentredString(width / 2, height - 95, "VENUS LUNA")

    # Ligne décorative
    p.setStrokeColor(colors.HexColor("#d4af37"))
    p.setLineWidth(1)
    p.line(width / 2 - 120, height - 105, width / 2 + 120, height - 105)

    # Titre du document
    p.setFont("Helvetica", 14)
    p.setFillColor(colors.HexColor("#4a5568"))
    p.drawCentredString(width / 2, height - 145, "CERTIFICAT DE RÉUSSITE & D'ACCOMPLISSEMENT")

    p.setFont("Helvetica", 11)
    p.setFillColor(colors.HexColor("#718096"))
    p.drawCentredString(width / 2, height - 170, "Le présent certificat atteste avec honneur que")

    # Nom de l'apprenant
    student_name = certificate.enrollment.user.get_full_name() or certificate.enrollment.user.username
    p.setFont("Helvetica-Bold", 24)
    p.setFillColor(colors.HexColor("#1c2541"))
    p.drawCentredString(width / 2, height - 210, student_name.upper())

    p.setStrokeColor(colors.HexColor("#d4af37"))
    p.setLineWidth(0.8)
    p.line(width / 2 - 160, height - 220, width / 2 + 160, height - 220)

    # Description de l'accomplissement
    p.setFont("Helvetica", 11)
    p.setFillColor(colors.HexColor("#718096"))
    p.drawCentredString(width / 2, height - 250, "a suivi avec succès l'ensemble des modules d'apprentissage et validé les évaluations de :")

    # Titre de la formation
    p.setFont("Helvetica-Bold", 20)
    p.setFillColor(colors.HexColor("#1c683b"))
    p.drawCentredString(width / 2, height - 285, f"« {certificate.enrollment.course.title} »")

    # Détails (Durée & Date)
    duration_hrs = certificate.enrollment.course.estimated_duration_hours
    date_str = certificate.issued_at.strftime("%d/%m/%Y")
    p.setFont("Helvetica", 10)
    p.setFillColor(colors.HexColor("#4a5568"))
    p.drawCentredString(width / 2, height - 315, f"Programme certifiant ({duration_hrs}h de formation) — Délivré le {date_str}")

    # Signatures & Mentions officielles
    y_signatures = 140

    # Formateur / Direction
    instructor_name = "La Direction Pédagogique"
    if certificate.enrollment.course.instructor:
        instructor_name = certificate.enrollment.course.instructor.get_full_name() or certificate.enrollment.course.instructor.username

    p.setFont("Helvetica-Bold", 11)
    p.setFillColor(colors.HexColor("#1c683b"))
    p.drawString(90, y_signatures, "Formateur Référent")
    p.setFont("Helvetica", 10)
    p.setFillColor(colors.HexColor("#2d3748"))
    p.drawString(90, y_signatures - 18, instructor_name)
    p.setFont("Helvetica-Oblique", 9)
    p.drawString(90, y_signatures - 32, "Venus Luna Academy")
    p.setStrokeColor(colors.HexColor("#cbd5e0"))
    p.line(90, y_signatures - 6, 230, y_signatures - 6)

    # Identifiant unique du certificat (Bas centre)
    p.setFont("Helvetica-Bold", 10)
    p.setFillColor(colors.HexColor("#d4af37"))
    p.drawCentredString(width / 2, 85, f"Identifiant Unique : {certificate.certificate_code}")

    p.setFont("Helvetica", 8)
    p.setFillColor(colors.HexColor("#a0aec0"))
    verification_url = f"https://venus-luna.com{certificate.get_verification_url()}"
    p.drawCentredString(width / 2, 70, f"Authenticité vérifiable sur {verification_url}")

    # QR Code de vérification publique (généré directement via ReportLab)
    try:
        qr_widget = qr.QrCodeWidget(verification_url)
        qr_widget.barWidth = 65
        qr_widget.barHeight = 65
        qr_widget.qrVersion = 2
        d = Drawing(65, 65)
        d.add(qr_widget)
        # Rendu du QR Code en bas à droite
        from reportlab.graphics import renderPDF
        renderPDF.draw(d, p, width - 180, 75)
        p.setFont("Helvetica", 8)
        p.setFillColor(colors.HexColor("#718096"))
        p.drawString(width - 180, 65, "Scannez pour vérifier")
    except Exception as qr_err:
        logger.warning(f"Impossible de générer le QR code pour le certificat {certificate.certificate_code}: {qr_err}")

    p.showPage()
    p.save()

    pdf_bytes = buffer.getvalue()
    buffer.close()
    return pdf_bytes

