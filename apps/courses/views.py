import json
import logging
from decimal import Decimal

from django.shortcuts import render, get_object_or_404, redirect
from django.urls import reverse
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import HttpResponse, JsonResponse, Http404
from django.db.models import Count, Q, Avg
from django.utils import timezone
from django.views.decorators.http import require_POST
from django.core import signing

from apps.core.ratelimit import ratelimit
from apps.orders.models import Order, OrderItem, ShippingAddress
from apps.orders.cashpay_service import CashPayService

from .models import (
    CourseCategory, Course, CourseModule, Lesson,
    Enrollment, LessonProgress,
    Quiz, QuizQuestion, QuizAnswerOption, QuizAttempt,
    Certificate,
)
from .services import (
    can_user_access_lesson,
    enroll_student_in_course,
    record_lesson_progress,
    evaluate_quiz_submission,
    issue_certificate_for_enrollment,
)

logger = logging.getLogger(__name__)


# ==============================================================================
# CATALOGUE PUBLIC DES FORMATIONS
# ==============================================================================

def course_list(request):
    """Catalogue public des formations disponibles sur Venus Luna."""
    categories = CourseCategory.objects.all().order_by('order', 'name')
    courses = Course.objects.filter(status=Course.Status.PUBLISHED).select_related('category', 'instructor')

    # Filtre par catégorie
    cat_slug = request.GET.get('category')
    selected_category = None
    if cat_slug:
        selected_category = get_object_or_404(CourseCategory, slug=cat_slug)
        courses = courses.filter(category=selected_category)

    # Filtre par niveau
    level = request.GET.get('level')
    if level in dict(Course.Level.choices):
        courses = courses.filter(level=level)

    # Filtre gratuit / payant
    pricing = request.GET.get('pricing')
    if pricing == 'free':
        courses = courses.filter(is_free=True)
    elif pricing == 'paid':
        courses = courses.filter(is_free=False)

    # Recherche textuelle
    query = request.GET.get('q', '').strip()
    if query:
        courses = courses.filter(
            Q(title__icontains=query) |
            Q(short_description__icontains=query) |
            Q(description__icontains=query)
        )

    context = {
        'courses': courses,
        'categories': categories,
        'selected_category': selected_category,
        'selected_level': level,
        'selected_pricing': pricing,
        'query': query,
    }
    return render(request, 'courses/course_list.html', context)


def course_detail(request, slug):
    """Présentation détaillée d'une formation, objectifs, modules et accès."""
    course = get_object_or_404(
        Course.objects.select_related('category', 'instructor').prefetch_related(
            'modules__lessons'
        ),
        slug=slug
    )

    # Si la formation n'est pas publiée, seuls les administrateurs et le formateur y accèdent
    if course.status != Course.Status.PUBLISHED:
        if not (request.user.is_authenticated and (request.user.is_staff or course.instructor_id == request.user.id)):
            raise Http404("Cette formation n'est pas disponible pour le moment.")

    # Vérification de l'inscription existante
    user_enrollment = None
    if request.user.is_authenticated:
        user_enrollment = Enrollment.objects.filter(
            user=request.user,
            course=course,
            status__in=[Enrollment.Status.ACTIVE, Enrollment.Status.COMPLETED],
        ).first()

    modules = course.modules.filter(is_published=True).prefetch_related('lessons')

    context = {
        'course': course,
        'modules': modules,
        'user_enrollment': user_enrollment,
        'total_lessons': course.total_lessons_count,
        'total_duration': course.total_duration_minutes,
        'objectives_list': course.get_objectives_list(),
        'prerequisites_list': course.get_prerequisites_list(),
    }
    return render(request, 'courses/course_detail.html', context)


# ==============================================================================
# INSCRIPTION ET ACHAT CASHPAY
# ==============================================================================

@login_required
@ratelimit(rate='10/m', key='ip', block=True, error_message="Trop de requêtes. Veuillez patienter un instant.")
def buy_course(request, slug):
    """
    Initialisation du paiement CashPay pour une formation payante.
    Crée une commande numérique liée à l'utilisateur et redirige vers la passerelle CashPay.
    """
    course = get_object_or_404(Course, slug=slug, status=Course.Status.PUBLISHED)

    # Si déjà inscrit, redirection directe vers le cours
    existing = Enrollment.objects.filter(
        user=request.user,
        course=course,
        status__in=[Enrollment.Status.ACTIVE, Enrollment.Status.COMPLETED]
    ).first()
    if existing:
        messages.info(request, "Vous êtes déjà inscrit à cette formation.")
        resume_lesson = existing.get_resume_lesson()
        if resume_lesson:
            return redirect(resume_lesson.get_absolute_url())
        return redirect('courses:student_dashboard')

    # Si la formation est gratuite, basculer sur l'inscription gratuite
    if course.is_free or course.price == 0:
        return redirect('courses:enroll_free', slug=course.slug)

    try:
        # Création de la commande numérique
        order = Order.objects.create(
            user=request.user,
            email=request.user.email or f"{request.user.username}@client.venus-luna.com",
            status='pending',
            payment_status=False,
            shipping_price=Decimal("0"),
            notes=f"Achat formation numérique : {course.title}",
        )

        OrderItem.objects.create(
            order=order,
            course=course,
            product=None,
            name=f"Formation : {course.title}",
            price=course.price,
            quantity=1,
        )

        order.recalc_total()

        # Adresse virtuelle pour compatibilité du modèle de commande
        user_phone = getattr(request.user.profile, 'phone', '') if hasattr(request.user, 'profile') else ''
        ShippingAddress.objects.create(
            order=order,
            full_name=request.user.get_full_name() or request.user.username,
            phone=user_phone,
            address="Accès numérique en ligne",
            city="Lomé",
            country="Togo",
        )

        request.session['last_order_id'] = order.id

        # Initialisation CashPay
        cashpay = CashPayService()
        if not cashpay.is_configured():
            logger.error("CashPay non configuré lors de l'achat d'une formation.")
            messages.error(request, "Le service de paiement est temporairement indisponible. Veuillez réessayer plus tard.")
            order.delete()
            return redirect('courses:course_detail', slug=course.slug)

        callback_url = getattr(settings, 'CASHPAY_WEBHOOK_URL', None) or request.build_absolute_uri(reverse('orders:cashpay_webhook'))
        token = signing.dumps(order.id, salt='cashpay-return')
        redirect_url = request.build_absolute_uri(
            reverse('orders:cashpay_return', kwargs={'order_id': order.id})
        ) + f"?token={token}"

        raw_phone = user_phone.strip() if user_phone else ''
        if raw_phone and not raw_phone.startswith('+'):
            raw_phone = f"+{raw_phone}"

        resp = cashpay.create_link2pay_order(
            amount=order.total,
            currency='XOF',
            merchant_reference=str(order.id),
            description=f"Formation Venus Luna : {course.title[:40]}",
            callback_url=callback_url,
            phone=raw_phone or "+22890000000",
            type_notif=["SMS", "MAIL"],
            redirect_url=redirect_url,
        )

        payment_url = resp.get('bill_url') or resp.get('payment_url')
        cashpay_order_ref = resp.get('order_reference', '')

        if not payment_url:
            raise RuntimeError("CashPay n'a pas retourné d'URL de facture (bill_url).")

        Order.objects.filter(id=order.id).update(
            payment_url=payment_url,
            paygate_tx_id=cashpay_order_ref or None
        )

        request.session['cashpay_bill_url'] = payment_url
        request.session['cashpay_order_ref'] = cashpay_order_ref

        # Redirection vers la page de paiement relais Venus Luna
        return redirect(reverse('orders:cashpay_payment_page', kwargs={'order_id': order.id}))

    except Exception as e:
        logger.error(f"Erreur initialisation paiement formation {course.id} : {e}", exc_info=True)
        messages.error(
            request,
            "Une erreur est survenue lors de l'initialisation du paiement. Veuillez réessayer dans quelques instants."
        )
        return redirect('courses:course_detail', slug=course.slug)


@login_required
@require_POST
def enroll_free_course(request, slug):
    """Inscription directe à une formation gratuite."""
    course = get_object_or_404(Course, slug=slug, status=Course.Status.PUBLISHED)

    if not course.is_free and course.price > 0:
        messages.error(request, "Cette formation est payante et requiert un règlement.")
        return redirect('courses:buy_course', slug=course.slug)

    enrollment, created = enroll_student_in_course(request.user, course, source=Enrollment.Source.FREE)
    if created:
        messages.success(request, f"Félicitations ! Vous êtes inscrit(e) à la formation « {course.title} ».")
    else:
        messages.info(request, f"Vous êtes déjà inscrit(e) à « {course.title} ».")

    resume_lesson = enrollment.get_resume_lesson()
    if resume_lesson:
        return redirect(resume_lesson.get_absolute_url())
    return redirect('courses:student_dashboard')


# ==============================================================================
# ESPACE PERSONNEL APPRENANT
# ==============================================================================

@login_required
def student_dashboard(request):
    """
    Espace personnel de l'apprenant :
    - Statistiques de progression globale.
    - Formations en cours avec bouton de reprise direct.
    - Formations terminées.
    - Certificats obtenus avec téléchargement immédiat.
    """
    enrollments = (
        Enrollment.objects.filter(user=request.user)
        .select_related('course', 'last_accessed_lesson', 'certificate')
        .prefetch_related('progresses')
        .order_by('-last_activity_at')
    )

    active_enrollments = [e for e in enrollments if e.status == Enrollment.Status.ACTIVE]
    completed_enrollments = [e for e in enrollments if e.status == Enrollment.Status.COMPLETED]

    # Calcul de la progression moyenne
    total_enrolled = len(enrollments)
    if total_enrolled > 0:
        avg_progress = int(sum(e.get_progress_percentage() for e in enrollments) / total_enrolled)
    else:
        avg_progress = 0

    certificates = Certificate.objects.filter(enrollment__user=request.user, is_valid=True).select_related('enrollment__course')

    context = {
        'total_enrolled': total_enrolled,
        'active_count': len(active_enrollments),
        'completed_count': len(completed_enrollments),
        'avg_progress': avg_progress,
        'active_enrollments': active_enrollments,
        'completed_enrollments': completed_enrollments,
        'certificates': certificates,
    }
    return render(request, 'courses/student_dashboard.html', context)


# ==============================================================================
# INTERFACE D'APPRENTISSAGE (CLASSROOM PLAYER)
# ==============================================================================

@login_required
def lesson_view(request, course_slug, lesson_id):
    """
    Interface de visionnage immersive d'une leçon :
    - Lecteur vidéo sécurisé ou contenu interactif.
    - Arborescence complète des modules et leçons avec statut de complétion.
    - Navigation Précédente / Suivante.
    - Quiz d'évaluation associé.
    """
    course = get_object_or_404(Course, slug=course_slug)
    lesson = get_object_or_404(Lesson.objects.select_related('module__course'), id=lesson_id, module__course=course)

    # Contrôle d'accès strict
    if not can_user_access_lesson(request.user, lesson):
        messages.warning(
            request,
            "Vous devez être inscrit(e) à cette formation pour accéder à cette leçon."
        )
        return redirect('courses:course_detail', slug=course.slug)

    # Récupérer l'inscription active pour enregistrer la consultation
    enrollment = Enrollment.objects.filter(
        user=request.user,
        course=course,
        status__in=[Enrollment.Status.ACTIVE, Enrollment.Status.COMPLETED]
    ).first()

    lesson_progress = None
    if enrollment:
        lesson_progress, _ = LessonProgress.objects.get_or_create(
            enrollment=enrollment,
            lesson=lesson,
        )
        # Mémoriser la dernière leçon consultée
        enrollment.last_accessed_lesson = lesson
        enrollment.last_activity_at = timezone.now()
        enrollment.save(update_fields=['last_accessed_lesson', 'last_activity_at'])

    modules = course.modules.filter(is_published=True).prefetch_related('lessons')

    # Liste des IDs de leçons terminées par l'apprenant
    completed_lesson_ids = set()
    if enrollment:
        completed_lesson_ids = set(
            enrollment.progresses.filter(is_completed=True).values_list('lesson_id', flat=True)
        )

    # Vérification d'un quiz associé à la leçon
    quiz = getattr(lesson, 'quiz', None)
    quiz_attempt = None
    if quiz and enrollment:
        quiz_attempt = enrollment.quiz_attempts.filter(quiz=quiz).order_by('-submitted_at').first()

    previous_lesson = lesson.get_previous_lesson()
    next_lesson = lesson.get_next_lesson()

    context = {
        'course': course,
        'lesson': lesson,
        'modules': modules,
        'enrollment': enrollment,
        'lesson_progress': lesson_progress,
        'completed_lesson_ids': completed_lesson_ids,
        'previous_lesson': previous_lesson,
        'next_lesson': next_lesson,
        'quiz': quiz,
        'quiz_attempt': quiz_attempt,
        'progress_percentage': enrollment.get_progress_percentage() if enrollment else 0,
    }
    return render(request, 'courses/lesson_player.html', context)


@login_required
@require_POST
def mark_lesson_completed(request, lesson_id):
    """Endpoint AJAX / Formulaire pour marquer une leçon comme terminée."""
    lesson = get_object_or_404(Lesson.objects.select_related('module__course'), id=lesson_id)

    try:
        progress, _ = record_lesson_progress(request.user, lesson, is_completed=True)
        enrollment = progress.enrollment
        pct = enrollment.get_progress_percentage()

        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({
                'success': True,
                'completed': True,
                'progress_percentage': pct,
                'course_completed': (enrollment.status == Enrollment.Status.COMPLETED),
            })

        messages.success(request, f"Leçon « {lesson.title} » validée !")
        next_lesson = lesson.get_next_lesson()
        if next_lesson:
            return redirect(next_lesson.get_absolute_url())
        return redirect('courses:student_dashboard')

    except Exception as e:
        logger.error(f"Erreur validation leçon {lesson_id} pour {request.user.username}: {e}")
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'success': False, 'error': str(e)}, status=400)
        messages.error(request, "Une erreur est survenue lors de l'enregistrement de votre progression.")
        return redirect(lesson.get_absolute_url())


# ==============================================================================
# QUIZ ET ÉVALUATIONS
# ==============================================================================

@login_required
@require_POST
@ratelimit(rate='6/m', key='ip', block=True, error_message="Trop de soumissions de quiz. Veuillez patienter une minute.")
def submit_quiz(request, quiz_id):
    """
    Traitement sécurisé de soumission d'un quiz :
    - Validation CSRF automatique Django.
    - Évaluation et notation 100% côté serveur.
    """
    quiz = get_object_or_404(Quiz.objects.select_related('lesson__module__course'), id=quiz_id)
    course = quiz.lesson.module.course

    # Recherche d'une inscription active ou complétée
    enrollment = Enrollment.objects.filter(
        user=request.user,
        course=course,
        status__in=[Enrollment.Status.ACTIVE, Enrollment.Status.COMPLETED]
    ).first()

    # Gestion des utilisateurs non encore inscrits
    if not enrollment:
        # 1. Formation gratuite : inscription automatique directe et sécurisée
        if course.is_free or course.price == 0:
            enrollment, _ = enroll_student_in_course(
                request.user,
                course,
                source=Enrollment.Source.FREE
            )
            logger.info(
                f"Inscription gratuite créée lors de la soumission du quiz pour {request.user.username} sur « {course.title} »"
            )

        # 2. Staff / Superuser ou formateur du cours : inscription administrative de test
        elif request.user.is_staff or request.user.is_superuser or course.instructor_id == request.user.id:
            enrollment, _ = enroll_student_in_course(
                request.user,
                course,
                source=Enrollment.Source.MANUAL_ADMIN
            )
            logger.info(
                f"Inscription administrative de test créée pour {request.user.username} sur « {course.title} »"
            )

        # 3. Utilisateur non inscrit sur formation payante : refus sécurisé et redirection
        else:
            messages.warning(
                request,
                f"Vous devez acquérir la formation « {course.title} » pour pouvoir participer à ce quiz d'évaluation."
            )
            return redirect('courses:buy_course', slug=course.slug)

    # Vérification de la limite de tentatives si configurée
    if quiz.max_attempts > 0:
        past_attempts = enrollment.quiz_attempts.filter(quiz=quiz).count()
        if past_attempts >= quiz.max_attempts:
            messages.error(request, f"Vous avez atteint la limite maximale de {quiz.max_attempts} tentative(s) pour ce quiz.")
            return redirect(quiz.lesson.get_absolute_url())

    # Extraction des réponses du formulaire POST
    user_answers = {}
    for question in quiz.questions.all():
        field_name = f"question_{question.id}"
        if question.question_type == question.QuestionType.SINGLE:
            val = request.POST.get(field_name)
            if val:
                user_answers[str(question.id)] = val
        else:
            vals = request.POST.getlist(field_name)
            if vals:
                user_answers[str(question.id)] = vals

    attempt = evaluate_quiz_submission(enrollment, quiz, user_answers)

    if attempt.passed:
        messages.success(
            request,
            f"Félicitations ! Vous avez réussi le quiz avec un score de {attempt.score}% (Minimum requis : {quiz.passing_score}%)."
        )
    else:
        messages.warning(
            request,
            f"Votre score est de {attempt.score}% (Minimum requis : {quiz.passing_score}%). Vous pouvez réviser et retenter le quiz."
        )

    return redirect(quiz.lesson.get_absolute_url())


# ==============================================================================
# CERTIFICATS (TÉLÉCHARGEMENT & VÉRIFICATION PUBLIQUE)
# ==============================================================================

@login_required
def download_certificate(request, certificate_code):
    """Téléchargement du certificat PDF par son propriétaire légitime."""
    certificate = get_object_or_404(
        Certificate.objects.select_related('enrollment__user', 'enrollment__course'),
        certificate_code=certificate_code,
        is_valid=True
    )

    # Contrôle d'accès : seul l'apprenant ou un membre staff peut télécharger son certificat
    if certificate.enrollment.user_id != request.user.id and not request.user.is_staff:
        raise Http404("Certificat introuvable.")

    if not certificate.pdf_file:
        # Régénération à la volée si manquant
        issue_certificate_for_enrollment(certificate.enrollment)
        certificate.refresh_from_db()

    try:
        response = HttpResponse(certificate.pdf_file.read(), content_type='application/pdf')
        filename = f"Certificat_VenusLuna_{certificate.certificate_code}.pdf"
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        return response
    except Exception as e:
        logger.error(f"Erreur lecture fichier certificat {certificate.certificate_code}: {e}")
        # En cas d'indisponibilité du stockage de fichier, régénération directe en mémoire
        from .services import build_certificate_pdf_bytes
        pdf_bytes = build_certificate_pdf_bytes(certificate)
        response = HttpResponse(pdf_bytes, content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="Certificat_VenusLuna_{certificate.certificate_code}.pdf"'
        return response


def verify_certificate(request, code):
    """
    Page publique de vérification d'authenticité d'un certificat.
    Affiche la validité, la date et la formation sans divulguer d'informations personnelles sensibles.
    """
    certificate = Certificate.objects.filter(
        certificate_code=code.strip()
    ).select_related('enrollment__course', 'enrollment__user').first()

    context = {
        'certificate': certificate,
        'code': code,
    }
    return render(request, 'courses/verify_certificate.html', context)

