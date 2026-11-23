import logging
from django import forms
from django.contrib import admin, messages
from django.http import HttpResponseRedirect
from django.core.files.uploadedfile import UploadedFile
from django.utils.html import format_html, mark_safe
from django.utils import timezone
from .models import (
    CourseCategory, Course, CourseModule, Lesson,
    Enrollment, LessonProgress,
    Quiz, QuizQuestion, QuizAnswerOption, QuizAttempt,
    Certificate, CourseRevision, CourseRevisionEvent, AccessGrant,
)
from .image_utils import validate_course_cover_image, optimize_course_cover_image

logger = logging.getLogger(__name__)


class CourseAdminForm(forms.ModelForm):
    """Formulaire d'administration pour Course avec validation et optimisation de l'image."""
    class Meta:
        model = Course
        fields = '__all__'

    def clean_cover_image(self):
        cover_image = self.cleaned_data.get('cover_image')
        if cover_image and isinstance(cover_image, UploadedFile):
            # 1. Validation de conformité (format, intégrité, taille maximale de sécurité)
            validate_course_cover_image(cover_image)
            # 2. Optimisation immédiate (redimensionnement max 1920x1080, WebP, qualité 80-85, cible < 500 Ko)
            cover_image = optimize_course_cover_image(cover_image)
        return cover_image


@admin.register(CourseCategory)
class CourseCategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug', 'icon_preview', 'order', 'created_at')
    list_editable = ('order',)
    search_fields = ('name', 'description')
    prepopulated_fields = {'slug': ('name',)}

    def icon_preview(self, obj):
        if obj.icon:
            return format_html('<i class="fas {}" style="font-size: 1.2rem; color: #1c683b;"></i> {}', obj.icon, obj.icon)
        return "-"
    icon_preview.short_description = "Icône"


class CourseModuleInline(admin.StackedInline):
    model = CourseModule
    extra = 1
    fields = ('title', 'order', 'is_published', 'description')
    ordering = ('order',)


class LessonInline(admin.TabularInline):
    model = Lesson
    extra = 1
    fields = ('title', 'lesson_type', 'duration_minutes', 'order', 'is_free_preview', 'is_published')
    ordering = ('order',)
    show_change_link = True


@admin.register(Course)
class CourseAdmin(admin.ModelAdmin):
    form = CourseAdminForm
    list_display = (
        'title',
        'category',
        'instructor',
        'level',
        'price_display',
        'status_badge',
        'lessons_count',
        'published_at',
    )
    list_filter = ('status', 'is_free', 'level', 'category', 'instructor')
    search_fields = ('title', 'short_description', 'description')
    prepopulated_fields = {'slug': ('title',)}
    list_editable = ()
    actions = ['make_published', 'make_draft', 'make_archived', 'create_draft_revisions']
    inlines = [CourseModuleInline]

    fieldsets = (
        ("Présentation de la Formation", {
            'fields': ('title', 'slug', 'category', 'instructor', 'cover_image', 'level', 'estimated_duration_hours')
        }),
        ("Tarification & Modalités d'Accès", {
            'fields': ('is_free', 'price', 'old_price')
        }),
        ("Statut & Publication", {
            'fields': ('status', 'published_at', 'published_revision_display'),
            'description': "La visibilité commerciale (statut) est distincte du contenu pédagogique : "
                           "les apprenants voient exclusivement la révision publiée. Toute modification "
                           "des modules et leçons ci-dessous constitue la copie de travail, publiée via "
                           "le workflow des révisions.",
        }),
        ("Contenu & Pédagogie", {
            'fields': ('short_description', 'description', 'objectives', 'prerequisites', 'syllabus')
        }),
        ("Certification", {
            'fields': ('certificate_enabled', 'certificate_passing_score'),
            'classes': ('collapse',)
        }),
        ("Métadonnées", {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    readonly_fields = ('created_at', 'updated_at', 'published_revision_display')

    def published_revision_display(self, obj):
        if not obj or not obj.published_revision_id:
            return mark_safe('<span style="color:#dc3545;">Aucune révision publiée — formation ni visible ni achetable</span>')
        rev = obj.published_revision
        return format_html('Révision n°{} (publiée le {})', rev.revision_number,
                           timezone.localtime(rev.published_at).strftime('%d/%m/%Y %H:%M') if rev.published_at else '—')
    published_revision_display.short_description = "Révision publiée"

    @admin.action(description="Créer une révision brouillon (workflow de validation)")
    def create_draft_revisions(self, request, queryset):
        from .revisions import RevisionWorkflowError, create_draft_revision
        for course in queryset:
            try:
                rev = create_draft_revision(course, request.user)
                self.message_user(request, f"« {course.title} » : révision brouillon n°{rev.revision_number} créée.")
            except RevisionWorkflowError as exc:
                self.message_user(request, f"« {course.title} » : {exc}", level=messages.WARNING)

    def price_display(self, obj):
        if obj.is_free or obj.price == 0:
            return mark_safe('<span style="color: #28a745; font-weight: bold;">Gratuit</span>')
        return format_html('<b style="color: #d4af37;">{} F CFA</b>', obj.price)
    price_display.short_description = "Prix"

    def status_badge(self, obj):
        colors = {
            'draft': '#ffc107',
            'published': '#28a745',
            'archived': '#6c757d',
        }
        return format_html(
            '<span style="background: {}; color: white; padding: 3px 8px; border-radius: 10px; font-size: 11px; font-weight: bold;">{}</span>',
            colors.get(obj.status, '#6c757d'),
            obj.get_status_display().upper()
        )
    status_badge.short_description = "Statut"

    def lessons_count(self, obj):
        return obj.total_lessons_count
    lessons_count.short_description = "Leçons"

    @admin.action(description="Publier les formations sélectionnées")
    def make_published(self, request, queryset):
        queryset.update(status=Course.Status.PUBLISHED, published_at=timezone.now())
        missing = queryset.filter(published_revision__isnull=True).count()
        if missing:
            self.message_user(
                request,
                f"{missing} formation(s) sans révision publiée : elles resteront invisibles et non achetables "
                f"tant qu'une révision n'aura pas été approuvée puis publiée.",
                level=messages.WARNING,
            )

    @admin.action(description="Passer en brouillon les formations sélectionnées")
    def make_draft(self, request, queryset):
        queryset.update(status=Course.Status.DRAFT)

    @admin.action(description="Archiver les formations sélectionnées")
    def make_archived(self, request, queryset):
        queryset.update(status=Course.Status.ARCHIVED)

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        # Si formateur non-superadmin, il ne voit que ses formations
        if request.user.is_superuser:
            return qs
        if request.user.groups.filter(name='Formateurs').exists():
            return qs.filter(instructor=request.user)
        return qs

    def save_model(self, request, obj, form, change):
        """Enregistre le modèle en interceptant les erreurs de téléversement Cloudinary."""
        try:
            super().save_model(request, obj, form, change)
        except Exception as exc:
            logger.exception("Échec du téléversement Cloudinary lors de la sauvegarde de la formation: %s", exc)
            if change:
                # S'assurer que l'image existante n'est pas corrompue en restaurant la valeur en base
                old_instance = Course.objects.filter(pk=obj.pk).first()
                if old_instance:
                    obj.cover_image = old_instance.cover_image
            raise exc

    def changeform_view(self, request, object_id=None, form_url='', extra_context=None):
        """Capture les exceptions inattendues pour éviter un crash 500 et afficher une alerte élégante."""
        try:
            return super().changeform_view(request, object_id, form_url, extra_context)
        except Exception as exc:
            logger.error("Exception interceptée dans CourseAdmin.changeform_view : %s", exc)
            self.message_user(
                request,
                f"Une erreur est survenue lors de l'enregistrement ou de l'envoi de l'image vers Cloudinary : {exc}",
                level=messages.ERROR
            )
            return HttpResponseRedirect(request.path)


@admin.register(CourseModule)
class CourseModuleAdmin(admin.ModelAdmin):
    list_display = ('title', 'course', 'order', 'lessons_count', 'is_published')
    list_filter = ('course', 'is_published')
    search_fields = ('title', 'course__title')
    ordering = ('course', 'order')
    inlines = [LessonInline]

    def lessons_count(self, obj):
        return obj.lessons.count()
    lessons_count.short_description = "Nombre de leçons"


@admin.register(Lesson)
class LessonAdmin(admin.ModelAdmin):
    list_display = ('title', 'module_course', 'lesson_type', 'duration_minutes', 'order', 'is_free_preview', 'is_published')
    list_filter = ('module__course', 'lesson_type', 'is_free_preview', 'is_published')
    search_fields = ('title', 'description', 'content', 'module__title', 'module__course__title')
    prepopulated_fields = {'slug': ('title',)}
    ordering = ('module__course', 'module__order', 'order')

    fieldsets = (
        ("Rattachement", {
            'fields': ('module', 'title', 'slug', 'lesson_type', 'order')
        }),
        ("Paramètres de visibilité", {
            'fields': ('is_free_preview', 'is_published', 'duration_minutes')
        }),
        ("Contenu Vidéo / Téléchargement", {
            'fields': ('video_url', 'attachment_file', 'attachment_name')
        }),
        ("Contenu Pédagogique (Texte & Notes)", {
            'fields': ('description', 'content')
        }),
        ("Métadonnées", {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    readonly_fields = ('created_at', 'updated_at')

    def module_course(self, obj):
        return f"{obj.module.course.title} → {obj.module.title}"
    module_course.short_description = "Formation & Module"


class LessonProgressInline(admin.TabularInline):
    model = LessonProgress
    extra = 0
    readonly_fields = ('lesson', 'revision', 'is_completed', 'completed_at', 'last_position_seconds', 'last_accessed_at')
    can_delete = False


@admin.register(Enrollment)
class EnrollmentAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'user',
        'course',
        'status_badge',
        'progress_bar',
        'source',
        'enrolled_at',
        'last_activity_at',
    )
    list_filter = ('status', 'source', 'course')
    search_fields = ('user__username', 'user__email', 'course__title', 'order__id')
    readonly_fields = ('enrolled_at', 'progress_percentage_display', 'revision')
    inlines = [LessonProgressInline]

    fieldsets = (
        ("Apprenant & Formation", {
            'fields': ('user', 'course', 'order', 'status', 'source', 'revision')
        }),
        ("Progression & Activité", {
            'fields': ('progress_percentage_display', 'last_accessed_lesson', 'last_activity_at', 'completed_at')
        }),
        ("Échéance", {
            'fields': ('expires_at', 'enrolled_at')
        }),
    )

    def progress_bar(self, obj):
        pct = obj.get_progress_percentage()
        color = '#28a745' if pct == 100 else '#17a2b8' if pct > 50 else '#ffc107'
        return format_html(
            '<div style="background: #e9ecef; border-radius: 6px; width: 100px; height: 16px; overflow: hidden; display: inline-block; vertical-align: middle;">'
            '<div style="background: {}; width: {}%; height: 100%; text-align: center; color: white; font-size: 10px; line-height: 16px; font-weight: bold;"></div>'
            '</div> <span style="font-weight: bold; font-size: 11px;">{}%</span>',
            color, pct, pct
        )
    progress_bar.short_description = "Progression"

    def progress_percentage_display(self, obj):
        return f"{obj.get_progress_percentage()} %"
    progress_percentage_display.short_description = "Progression globale"

    def status_badge(self, obj):
        colors = {
            'active': '#28a745',
            'completed': '#155430',
            'expired': '#dc3545',
            'cancelled': '#6c757d',
        }
        return format_html(
            '<span style="background: {}; color: white; padding: 2px 8px; border-radius: 8px; font-size: 10px; font-weight: bold;">{}</span>',
            colors.get(obj.status, '#6c757d'),
            obj.get_status_display().upper()
        )
    status_badge.short_description = "Statut"


class QuizAnswerOptionInline(admin.TabularInline):
    model = QuizAnswerOption
    extra = 4
    fields = ('order', 'option_text', 'is_correct')
    ordering = ('order',)


@admin.register(QuizQuestion)
class QuizQuestionAdmin(admin.ModelAdmin):
    list_display = ('question_text_short', 'quiz', 'question_type', 'points', 'order')
    list_filter = ('quiz__lesson__module__course', 'question_type')
    search_fields = ('question_text', 'quiz__title')
    inlines = [QuizAnswerOptionInline]

    def question_text_short(self, obj):
        return obj.question_text[:80]
    question_text_short.short_description = "Question"


class QuizQuestionInline(admin.StackedInline):
    model = QuizQuestion
    extra = 1
    fields = ('order', 'question_text', 'question_type', 'points', 'explanation')
    ordering = ('order',)
    show_change_link = True


@admin.register(Quiz)
class QuizAdmin(admin.ModelAdmin):
    list_display = ('title', 'lesson', 'passing_score', 'questions_count', 'max_attempts', 'created_at')
    search_fields = ('title', 'lesson__title', 'lesson__module__course__title')
    inlines = [QuizQuestionInline]

    def questions_count(self, obj):
        return obj.questions.count()
    questions_count.short_description = "Questions"


@admin.register(QuizAttempt)
class QuizAttemptAdmin(admin.ModelAdmin):
    list_display = ('enrollment_user', 'quiz_title', 'score_display', 'passed_badge', 'attempt_number', 'submitted_at')
    list_filter = ('passed', 'quiz__lesson__module__course')
    search_fields = ('enrollment__user__username', 'quiz__title')
    readonly_fields = ('enrollment', 'quiz', 'revision', 'score', 'passed', 'attempt_number', 'submitted_at', 'attempt_snapshot')

    def has_change_permission(self, request, obj=None):
        # Un résultat d'évaluation n'est jamais modifiable a posteriori (consultation seule).
        return False

    def enrollment_user(self, obj):
        return obj.enrollment.user.username
    enrollment_user.short_description = "Apprenant"

    def quiz_title(self, obj):
        return obj.quiz.title
    quiz_title.short_description = "Quiz"

    def score_display(self, obj):
        return f"{obj.score} %"
    score_display.short_description = "Score"

    def passed_badge(self, obj):
        color = '#28a745' if obj.passed else '#dc3545'
        text = "RÉUSSI" if obj.passed else "ÉCHOUÉ"
        return format_html(
            '<span style="background: {}; color: white; padding: 2px 8px; border-radius: 8px; font-weight: bold; font-size: 10px;">{}</span>',
            color, text
        )
    passed_badge.short_description = "Résultat"


@admin.register(Certificate)
class CertificateAdmin(admin.ModelAdmin):
    list_display = ('certificate_code', 'student_name', 'course_title', 'issued_at', 'is_valid_badge', 'verify_link')
    list_filter = ('is_valid', 'enrollment__course')
    search_fields = ('certificate_code', 'enrollment__user__username', 'enrollment__user__email', 'enrollment__course__title')
    readonly_fields = ('certificate_code', 'issued_at')

    def student_name(self, obj):
        return obj.enrollment.user.get_full_name() or obj.enrollment.user.username
    student_name.short_description = "Apprenant"

    def course_title(self, obj):
        return obj.enrollment.course.title
    course_title.short_description = "Formation"

    def is_valid_badge(self, obj):
        if obj.is_valid:
            return mark_safe('<span style="color: #28a745; font-weight: bold;">✔ Valide</span>')
        return mark_safe('<span style="color: #dc3545; font-weight: bold;">✘ Révoqué</span>')
    is_valid_badge.short_description = "Validité"

    def verify_link(self, obj):
        url = obj.get_verification_url()
        return format_html('<a href="{}" target="_blank" style="color: #1c683b; font-weight: bold;">🔍 Vérifier</a>', url)
    verify_link.short_description = "Lien public"



# =============================================================================
# VERSIONNEMENT : RÉVISIONS ET WORKFLOW DE VALIDATION
# =============================================================================

class CourseRevisionEventInline(admin.TabularInline):
    model = CourseRevisionEvent
    fk_name = 'revision'
    extra = 0
    can_delete = False
    fields = ('created_at', 'action', 'actor', 'note', 'previous_published_revision')
    readonly_fields = fields

    def has_add_permission(self, request, obj=None):
        return False


def _format_changes(changes):
    from django.utils.html import format_html_join
    return format_html_join('', '<li>{} : {}</li>', ((kind, label) for kind, label in changes))


@admin.register(CourseRevision)
class CourseRevisionAdmin(admin.ModelAdmin):
    list_display = ('course', 'revision_number', 'status_badge', 'is_published_now', 'created_by',
                    'submitted_at', 'reviewed_by', 'published_at')
    list_filter = ('status', 'course')
    search_fields = ('course__title', 'change_summary')
    readonly_fields = ('course', 'revision_number', 'status', 'created_by', 'created_at', 'submitted_at',
                       'reviewed_by', 'reviewed_at', 'approved_at', 'published_at', 'content_hash',
                       'review_notes', 'diff_display', 'content_overview')
    fields = ('course', 'revision_number', 'status', 'change_summary', 'review_notes', 'diff_display',
              'content_overview', 'created_by', 'created_at', 'submitted_at', 'reviewed_by', 'reviewed_at',
              'approved_at', 'published_at', 'content_hash')
    inlines = [CourseRevisionEventInline]
    change_form_template = 'admin/courses/courserevision/change_form.html'

    def get_queryset(self, request):
        qs = super().get_queryset(request).select_related('course', 'created_by', 'reviewed_by')
        if not request.user.is_superuser and request.user.groups.filter(name='Formateurs').exists():
            return qs.filter(course__instructor=request.user)
        return qs

    def get_readonly_fields(self, request, obj=None):
        ro = list(self.readonly_fields)
        if obj is not None and obj.status != CourseRevision.Status.DRAFT:
            ro.append('change_summary')  # révision figée
        return ro

    def has_add_permission(self, request):
        return False  # création via l'action « Créer une révision brouillon » des formations

    def has_delete_permission(self, request, obj=None):
        # Aucune suppression : un brouillon abandonné est « retiré » (historique conservé).
        return False

    def status_badge(self, obj):
        colors = {'DRAFT': '#ffc107', 'SUBMITTED': '#17a2b8', 'APPROVED': '#28a745',
                  'REJECTED': '#dc3545', 'WITHDRAWN': '#6c757d'}
        return format_html('<span style="background:{};color:white;padding:2px 8px;border-radius:8px;'
                           'font-size:10px;font-weight:bold;">{}</span>',
                           colors.get(obj.status, '#6c757d'), obj.get_status_display().upper())
    status_badge.short_description = "Statut"

    def is_published_now(self, obj):
        return obj.course.published_revision_id == obj.pk
    is_published_now.boolean = True
    is_published_now.short_description = "En ligne"

    def diff_display(self, obj):
        from .content import build_snapshot, diff_snapshots
        if obj is None or obj.pk is None:
            return "-"
        published = obj.course.published_revision
        if published and published.pk == obj.pk:
            return "Cette révision est la révision publiée."
        new = obj.snapshot if obj.snapshot is not None else build_snapshot(obj.course)
        old = published.snapshot if published else None
        changes = diff_snapshots(old, new)
        if not changes:
            return "Aucune différence avec la révision publiée."
        ref = f"révision publiée n°{published.revision_number}" if published else "aucune révision publiée"
        return format_html("<div>Comparaison avec la {} :</div><ul>{}</ul>", ref, _format_changes(changes))
    diff_display.short_description = "Comparaison"

    def content_overview(self, obj):
        content = obj.get_content() if obj and obj.snapshot is not None else None
        if content is None:
            return "Brouillon : le contenu est la copie de travail de la formation (modules et leçons)."
        from django.utils.html import format_html_join
        rows = format_html_join(
            '', '<li><b>{}</b> — {}</li>',
            ((module.title, ", ".join(lesson.title for lesson in module.lessons)) for module in content.modules),
        )
        return format_html("<ul>{}</ul>", rows)
    content_overview.short_description = "Contenu figé"

    # -- Boutons de workflow ----------------------------------------------------

    def get_urls(self):
        from django.urls import path
        custom = [
            path('<int:pk>/workflow/<str:action>/', self.admin_site.admin_view(self.workflow_view),
                 name='courses_courserevision_workflow'),
        ]
        return custom + super().get_urls()

    def workflow_view(self, request, pk, action):
        from django.core.exceptions import PermissionDenied
        from django.shortcuts import get_object_or_404, render
        from django.urls import reverse
        from . import revisions as wf

        revision = get_object_or_404(self.get_queryset(request), pk=pk)
        if not self.has_view_permission(request, revision):
            raise PermissionDenied
        handlers = {
            'submit': lambda note: wf.submit_revision(revision, request.user),
            'withdraw': lambda note: wf.withdraw_revision(revision, request.user, note),
            'approve': lambda note: wf.approve_revision(revision, request.user, note),
            'reject': lambda note: wf.reject_revision(revision, request.user, note),
            'publish': lambda note: wf.publish_revision(revision, request.user, note),
        }
        if action not in handlers:
            raise PermissionDenied
        back = reverse('admin:courses_courserevision_change', args=[revision.pk])
        if request.method != 'POST':
            return render(request, 'admin/courses/courserevision/workflow_confirm.html', {
                **self.admin_site.each_context(request),
                'opts': self.model._meta, 'revision': revision, 'action': action,
                'note_required': action == 'reject',
                'title': f"Confirmer : {dict(WORKFLOW_LABELS).get(action, action)}",
            })
        try:
            handlers[action](request.POST.get('note', ''))
            self.message_user(request, "Action effectuée.", level=messages.SUCCESS)
        except wf.RevisionWorkflowError as exc:
            self.message_user(request, str(exc), level=messages.ERROR)
        return HttpResponseRedirect(back)

    def render_change_form(self, request, context, add=False, change=False, form_url='', obj=None):
        from . import revisions as wf
        if obj is not None:
            S = CourseRevision.Status
            actions = []
            if obj.status == S.DRAFT and wf.can_author(request.user, obj.course):
                actions += ['submit', 'withdraw']
            if obj.status == S.SUBMITTED:
                if wf.can_review(request.user):
                    actions += ['approve', 'reject']
                if wf.can_author(request.user, obj.course):
                    actions.append('withdraw')
            if obj.status == S.APPROVED and wf.can_publish(request.user) and obj.course.published_revision_id != obj.pk:
                actions.append('publish')
            labels = dict(WORKFLOW_LABELS)
            context['workflow_buttons'] = [(a, labels[a]) for a in actions]
        return super().render_change_form(request, context, add, change, form_url, obj)


WORKFLOW_LABELS = (
    ('submit', 'Soumettre pour validation'),
    ('withdraw', 'Retirer la révision'),
    ('approve', 'Approuver'),
    ('reject', 'Rejeter (motif obligatoire)'),
    ('publish', 'Publier cette révision'),
)


@admin.register(AccessGrant)
class AccessGrantAdmin(admin.ModelAdmin):
    list_display = ('user', 'course', 'revision', 'source', 'status', 'order_item', 'granted_at', 'revoked_at')
    list_filter = ('status', 'source', 'course')
    search_fields = ('user__username', 'user__email', 'course__title', 'order_item__order__id')
    readonly_fields = ('user', 'course', 'revision', 'enrollment', 'order_item', 'source', 'status',
                       'granted_at', 'granted_by', 'revoked_at', 'revoked_by', 'revocation_reason')
    actions = ['revoke_selected']

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    @admin.action(description="Révoquer les droits sélectionnés (historique conservé)")
    def revoke_selected(self, request, queryset):
        from django.db import transaction
        from .access import revoke_grant
        n = 0
        for grant in queryset.filter(status=AccessGrant.Status.ACTIVE):
            with transaction.atomic():
                if revoke_grant(grant, "Révocation manuelle (administration)", revoked_by=request.user):
                    n += 1
        self.message_user(request, f"{n} droit(s) révoqué(s).")
