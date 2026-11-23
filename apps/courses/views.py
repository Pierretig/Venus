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
from .access import AccessGrantError
from .content import ItemList
from .services import (
    can_user_access_lesson,
    enroll_student_in_course,
    get_active_enrollment,
    is_privileged,
    record_lesson_progress,
    resolve_content,
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
    courses = Course.objects.filter(
        status=Course.Status.PUBLISHED,
        published_revision__isnull=False,
    ).select_related('category', 'instructor', 'published_revision')

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
        Course.objects.select_related('category', 'instructor', 'published_revision'),
        slug=slug
    )

    # Formation non disponible (non publiée ou sans révision publiée) : staff et formateur uniquement
    privileged = is_privileged(request.user, course)
    user_enrollment = get_active_enrollment(request.user, course)
    if not course.is_available_for_learners and not privileged and user_enrollment is None:
        raise Http404("Cette formation n'est pas disponible pour le moment.")

    preview = privileged and request.GET.get('apercu') == 'brouillon'
    content = resolve_content(request.user, course, enrollment=user_enrollment, preview=preview)
    modules = content.modules if content is not None else ItemList()

    context = {
        'course': course,
        'modules': modules,
        'content': content,
        'is_working_copy_preview': content is not None and content.is_preview,
        'user_enrollment': user_enrollment,
        'total_lessons': content.total_lessons if content is not None else 0,
        'total_duration': content.total_duration_minutes if content is not None else 0,
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

    # Décision R3 : aucune vente sans version pédagogique identifiable.
    if course.published_revision_id is None:
        messages.error(request, "Cette formation n'est pas encore disponible à l'achat.")
        return redirect('courses:course_detail', slug=course.slug)

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

    try:
        enrollment, created = enroll_student_in_course(request.user, course, source=Enrollment.Source.FREE)
    except AccessGrantError:
        messages.error(request, "Cette formation n'est pas encore disponible.")
        return redirect('courses:course_detail', slug=course.slug)
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
        .select_related('course', 'course__published_revision', 'revision', 'last_accessed_lesson', 'certificate')
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
    Interface de visionnage immersive d'une leçon, servie depuis la révision figée
    suivie par l'apprenant (ou, pour le formateur / staff, depuis la révision publiée ou
    la copie de travail avec ?apercu=brouillon).
    """
    course = get_object_or_404(Course.objects.select_related('published_revision'), slug=course_slug)
    enrollment = get_active_enrollment(request.user, course)
    preview = is_privileged(request.user, course) and request.GET.get('apercu') == 'brouillon'
    content = resolve_content(request.user, course, enrollment=enrollment, preview=preview)
    lesson = content.get_lesson(lesson_id) if content is not None else None
    if lesson is None:
        raise Http404("Leçon introuvable dans la version de la formation qui vous est attribuée.")

    # Contrôle d'accès strict
    if not can_user_access_lesson(request.user, lesson):
        messages.warning(
            request,
            "Vous devez être inscrit(e) à cette formation pour accéder à cette leçon."
        )
        return redirect('courses:course_detail', slug=course.slug)

    lesson_progress = None
    completed_lesson_ids = set()
    if enrollment and not content.is_preview and Lesson.objects.filter(pk=lesson.id).exists():
        lesson_progress, _ = LessonProgress.objects.get_or_create(
            enrollment=enrollment,
            lesson_id=lesson.id,
            defaults={'revision': content.revision},
        )
        # Mémoriser la dernière leçon consultée
        enrollment.last_accessed_lesson_id = lesson.id
        enrollment.last_activity_at = timezone.now()
        enrollment.save(update_fields=['last_accessed_lesson', 'last_activity_at'])
    if enrollment:
        completed_lesson_ids = set(
            enrollment.progresses.filter(is_completed=True, lesson_id__in=content.lesson_ids)
            .values_list('lesson_id', flat=True)
        )

    quiz = lesson.quiz
    quiz_attempt = None
    if quiz and enrollment:
        quiz_attempt = enrollment.quiz_attempts.filter(quiz_id=quiz.id).order_by('-submitted_at').first()

    context = {
        'course': course,
        'lesson': lesson,
        'modules': content.modules,
        'content': content,
        'is_working_copy_preview': content.is_preview,
        'enrollment': enrollment,
        'lesson_progress': lesson_progress,
        'completed_lesson_ids': completed_lesson_ids,
        'previous_lesson': lesson.get_previous_lesson(),
        'next_lesson': lesson.get_next_lesson(),
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
        content = enrollment.get_content()
        lesson = content.get_lesson(lesson.id) or lesson

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

    except (PermissionError, AccessGrantError, ValueError) as e:
        logger.warning(f"Validation leçon {lesson_id} refusée pour {request.user.username}: {e}")
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
    live_quiz = get_object_or_404(Quiz.objects.select_related('lesson__module__course'), id=quiz_id)
    course = live_quiz.lesson.module.course

    # Recherche d'une inscription active ou complétée
    enrollment = get_active_enrollment(request.user, course)

    # Gestion des utilisateurs non encore inscrits
    if not enrollment:
        try:
            # 1. Formation gratuite : inscription automatique directe et sécurisée
            if course.is_free or course.price == 0:
                enrollment, _ = enroll_student_in_course(request.user, course, source=Enrollment.Source.FREE)
                logger.info(
                    f"Inscription gratuite créée lors de la soumission du quiz pour {request.user.username} sur « {course.title} »"
                )
            # 2. Staff / Superuser ou formateur du cours : inscription administrative de test
            elif request.user.is_staff or request.user.is_superuser or course.instructor_id == request.user.id:
                enrollment, _ = enroll_student_in_course(request.user, course, source=Enrollment.Source.MANUAL_ADMIN)
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
        except AccessGrantError:
            messages.error(request, "Cette formation n'est pas encore disponible.")
            return redirect('courses:course_detail', slug=course.slug)
        enrollment = get_active_enrollment(request.user, course)

    # Le quiz évalué est celui de la révision suivie, jamais celui de la copie de travail.
    content = enrollment.get_content()
    quiz = content.get_quiz(live_quiz.id) if content is not None else None
    if quiz is None:
        messages.error(request, "Ce quiz ne fait pas partie de la version de la formation qui vous est attribuée.")
        return redirect('courses:course_detail', slug=course.slug)

    # Vérification de la limite de tentatives si configurée (règle de la révision suivie)
    if quiz.max_attempts > 0:
        past_attempts = enrollment.quiz_attempts.filter(quiz_id=quiz.id).count()
        if past_attempts >= quiz.max_attempts:
            messages.error(request, f"Vous avez atteint la limite maximale de {quiz.max_attempts} tentative(s) pour ce quiz.")
            return redirect(quiz.lesson.get_absolute_url())

    # Extraction des réponses du formulaire POST
    user_answers = {}
    for question in quiz.questions:
        field_name = f"question_{question.id}"
        if question.question_type == 'single':
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



@login_required
def quiz_attempt_detail(request, attempt_id):
    """
    Consultation d'une tentative passée, restituée depuis son contexte figé :
    questions présentées, réponses choisies, bonnes réponses au moment de l'évaluation.
    Les tentatives historiques (antérieures au versionnement) n'affichent que le score.
    """
    attempt = get_object_or_404(
        QuizAttempt.objects.select_related('enrollment__user', 'enrollment__course', 'quiz', 'revision'),
        id=attempt_id,
    )
    if attempt.enrollment.user_id != request.user.id and not request.user.is_staff:
        raise Http404("Tentative introuvable.")

    questions = []
    if attempt.attempt_snapshot:
        for q in attempt.attempt_snapshot.get('questions', []):
            selected = set(q.get('selected_option_ids', []))
            correct = set(q.get('correct_option_ids', []))
            options = [
                dict(o, selected=o['id'] in selected, correct=o['id'] in correct)
                for o in q.get('options', [])
            ]
            questions.append(dict(q, options=options))

    context = {
        'attempt': attempt,
        'course': attempt.enrollment.course,
        'questions': questions,
        'snapshot': attempt.attempt_snapshot or {},
    }
    return render(request, 'courses/quiz_attempt_detail.html', context)
