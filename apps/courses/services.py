import io
import logging
from decimal import Decimal
from typing import Tuple, Dict, Any, Optional

from django.conf import settings
from django.db import transaction
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
from .access import AccessGrantError, grant_non_purchase_access

logger = logging.getLogger(__name__)

QUIZ_SCORING_RULE = "all_or_nothing_per_question_v1"
ATTEMPT_SNAPSHOT_SCHEMA_VERSION = 1
_ACCESS_STATUSES = [Enrollment.Status.ACTIVE, Enrollment.Status.COMPLETED]


# ==============================================================================
# RÉSOLUTION DU CONTENU VERSIONNÉ
# ==============================================================================

def is_privileged(user, course) -> bool:
    """Staff, superutilisateur ou formateur responsable de la formation."""
    if not (user and user.is_authenticated):
        return False
    return bool(user.is_staff or user.is_superuser or course.instructor_id == user.id)


def get_active_enrollment(user, course) -> Optional[Enrollment]:
    if not (user and user.is_authenticated):
        return None
    return (
        Enrollment.objects.select_related('revision', 'course__published_revision')
        .filter(user=user, course=course, status__in=_ACCESS_STATUSES)
        .first()
    )


def resolve_content(user, course, enrollment=None, preview=False):
    """
    Détermine le contenu pédagogique servi à un utilisateur :
    - apprenant inscrit : révision de son inscription (historique : révision publiée courante) ;
    - formateur / staff demandant un aperçu, ou sans révision publiée : copie de travail ;
    - sinon : révision publiée (None si la formation n'a aucune révision publiée).
    """
    if enrollment is None:
        enrollment = get_active_enrollment(user, course)
    if preview and is_privileged(user, course):
        return course.get_working_copy_content()
    if enrollment is not None:
        content = enrollment.get_content()
        if content is not None:
            return content
    content = course.get_published_content()
    if content is None and is_privileged(user, course):
        return course.get_working_copy_content()
    return content


def _lesson_course(lesson):
    return lesson.module.course


def can_user_access_lesson(user, lesson) -> bool:
    """
    Contrôle d'accès strict à une leçon (modèle vivant ou vue de snapshot) :
    - Administrateurs / Staff / formateur responsable : accès total.
    - Aperçu gratuit de la révision servie : accessible à tous (y compris anonymes).
    - Apprenant : inscription active ET leçon présente dans la révision qu'il suit.
    """
    course = _lesson_course(lesson)
    if is_privileged(user, course):
        return True

    enrollment = get_active_enrollment(user, course)
    content = enrollment.get_content() if enrollment else course.get_published_content()
    if content is None:
        return False
    lesson_view = content.get_lesson(lesson.id)
    if lesson_view is None:
        return False
    if lesson_view.is_free_preview and (enrollment is not None or course.status == Course.Status.PUBLISHED):
        return True
    return enrollment is not None


# ==============================================================================
# INSCRIPTIONS
# ==============================================================================

def enroll_student_in_course(user, course: Course, source: str = 'free', order=None) -> Tuple[Enrollment, bool]:
    """
    Inscrit un apprenant à une formation de façon idempotente (accès gratuit ou manuel).
    Les accès payants sont créés exclusivement par la confirmation de commande.
    Lève AccessGrantError si la formation n'a pas de révision publiée.
    """
    if not user.is_authenticated:
        raise ValueError("L'utilisateur doit être connecté pour s'inscrire à une formation.")

    if source == Enrollment.Source.CASHPAY:
        raise PermissionError("Un accès payant ne peut être attribué que par une commande confirmée.")

    if not course.is_free and source == 'free' and not user.is_staff:
        raise PermissionError("Cette formation est payante et nécessite une commande validée.")

    enrollment, created, _grant = grant_non_purchase_access(user, course, source)
    return enrollment, created


def _ensure_enrollment_for_learning(user, course) -> Enrollment:
    enrollment = get_active_enrollment(user, course)
    if enrollment:
        return enrollment
    if course.is_free or course.price == 0:
        enrollment, _ = enroll_student_in_course(user, course, source=Enrollment.Source.FREE)
    elif user.is_staff or user.is_superuser or course.instructor_id == user.id:
        enrollment, _ = enroll_student_in_course(user, course, source=Enrollment.Source.MANUAL_ADMIN)
    else:
        raise PermissionError("L'utilisateur n'est pas inscrit à cette formation.")
    return get_active_enrollment(user, course)


# ==============================================================================
# PROGRESSION
# ==============================================================================

def record_lesson_progress(user, lesson, is_completed: bool = False, position_seconds: int = 0) -> Tuple[LessonProgress, bool]:
    """
    Enregistre ou met à jour la progression d'un apprenant sur une leçon de la révision
    qu'il suit. La révision concernée est enregistrée avec la progression.
    """
    course = _lesson_course(lesson)
    enrollment = _ensure_enrollment_for_learning(user, course)
    content = enrollment.get_content()
    if content is None or content.get_lesson(lesson.id) is None:
        raise PermissionError("Cette leçon ne fait pas partie de la révision suivie par l'apprenant.")
    if not Lesson.objects.filter(pk=lesson.id).exists():
        raise PermissionError("Cette leçon a été supprimée de la copie de travail : progression non enregistrable.")

    revision = content.revision
    progress, created = LessonProgress.objects.get_or_create(
        enrollment=enrollment,
        lesson_id=lesson.id,
        defaults={
            'is_completed': is_completed,
            'completed_at': timezone.now() if is_completed else None,
            'last_position_seconds': position_seconds,
            'revision': revision,
        }
    )

    update_fields = ['last_accessed_at']
    if position_seconds > 0:
        progress.last_position_seconds = position_seconds
        update_fields.append('last_position_seconds')

    if is_completed and not progress.is_completed:
        progress.is_completed = True
        progress.completed_at = timezone.now()
        progress.revision = revision
        update_fields.extend(['is_completed', 'completed_at', 'revision'])

    if not created:
        progress.save(update_fields=update_fields)

    enrollment.last_accessed_lesson_id = lesson.id
    enrollment.last_activity_at = timezone.now()
    enrollment.save(update_fields=['last_accessed_lesson', 'last_activity_at'])

    if is_completed:
        course_completed = enrollment.check_and_update_completion()
        if course_completed and enrollment.course.certificate_enabled:
            issue_certificate_for_enrollment(enrollment)

    return progress, created


# ==============================================================================
# QUIZ
# ==============================================================================

def _parse_selection(question, submitted):
    """Normalise la sélection de l'apprenant en identifiants d'options de la question."""
    valid_ids = {o.id for o in question.options}
    if submitted in (None, "", []):
        return []
    values = submitted if isinstance(submitted, (list, tuple)) else [submitted]
    if question.question_type == 'single':
        values = values[:1]
    selected = []
    for value in values:
        try:
            option_id = int(str(value).strip())
        except (ValueError, TypeError):
            continue
        if option_id in valid_ids and option_id not in selected:
            selected.append(option_id)
    return selected


def grade_quiz(quiz_view, user_answers: Dict[str, Any]):
    """
    Note une soumission contre le quiz d'une révision figée et retourne le contexte
    complet de la tentative (questions, options, sélections, bonnes réponses, points).
    Règle : une question rapporte ses points si la sélection est exactement l'ensemble
    des bonnes réponses (choix unique : l'option choisie est correcte).
    """
    questions = []
    total_points = 0
    earned_points = 0
    for question in quiz_view.questions:
        selected = _parse_selection(question, user_answers.get(str(question.id)))
        correct = sorted(question.correct_option_ids())
        is_correct = bool(correct) and set(selected) == set(correct)
        earned = question.points if is_correct else 0
        total_points += question.points
        earned_points += earned
        questions.append({
            'id': question.id,
            'question_text': question.question_text,
            'question_type': question.question_type,
            'points': question.points,
            'explanation': question.explanation,
            'options': [
                {'id': o.id, 'option_text': o.option_text, 'is_correct': o.is_correct}
                for o in question.options
            ],
            'selected_option_ids': selected,
            'correct_option_ids': correct,
            'is_correct': is_correct,
            'earned_points': earned,
        })

    score = Decimal("0.00")
    if total_points > 0:
        score = Decimal(str(round((earned_points / total_points) * 100, 2)))
    passed = score >= quiz_view.passing_score
    context = {
        'schema_version': ATTEMPT_SNAPSHOT_SCHEMA_VERSION,
        'scoring_rule': QUIZ_SCORING_RULE,
        'quiz': {
            'id': quiz_view.id,
            'title': quiz_view.title,
            'passing_score': quiz_view.passing_score,
        },
        'questions': questions,
        'total_points': total_points,
        'earned_points': earned_points,
        'score': str(score),
        'passed': passed,
    }
    return score, passed, context


def evaluate_quiz_submission(enrollment: Enrollment, quiz, user_answers: Dict[str, Any]) -> QuizAttempt:
    """
    Évalue les réponses d'un apprenant 100 % côté serveur contre le quiz de la révision
    qu'il suit, et enregistre une tentative autoportante (contexte figé) : une nouvelle
    révision ou une modification ultérieure des bonnes réponses ne modifie jamais ce résultat.
    """
    content = enrollment.get_content()
    quiz_view = content.get_quiz(quiz.id) if content is not None else None
    if quiz_view is None:
        raise PermissionError("Ce quiz ne fait pas partie de la révision suivie par l'apprenant.")
    if not Quiz.objects.filter(pk=quiz_view.id).exists():
        raise PermissionError("Ce quiz a été supprimé de la copie de travail : tentative non enregistrable.")

    score, passed, context = grade_quiz(quiz_view, user_answers)

    with transaction.atomic():
        attempts_count = enrollment.quiz_attempts.filter(quiz_id=quiz_view.id).count()
        attempt = QuizAttempt.objects.create(
            enrollment=enrollment,
            quiz_id=quiz_view.id,
            score=score,
            passed=passed,
            attempt_number=attempts_count + 1,
            revision=content.revision,
            attempt_snapshot=context,
        )

    if passed:
        record_lesson_progress(enrollment.user, quiz_view.lesson, is_completed=True)

    return attempt


# ==============================================================================
# CERTIFICATS
# ==============================================================================



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

