from django.contrib import admin
from django.utils.html import format_html, mark_safe
from django.utils import timezone
from .models import (
    CourseCategory, Course, CourseModule, Lesson,
    Enrollment, LessonProgress,
    Quiz, QuizQuestion, QuizAnswerOption, QuizAttempt,
    Certificate,
)


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
    actions = ['make_published', 'make_draft', 'make_archived']
    inlines = [CourseModuleInline]

    fieldsets = (
        ("Présentation de la Formation", {
            'fields': ('title', 'slug', 'category', 'instructor', 'cover_image', 'level', 'estimated_duration_hours')
        }),
        ("Tarification & Modalités d'Accès", {
            'fields': ('is_free', 'price', 'old_price')
        }),
        ("Statut & Publication", {
            'fields': ('status', 'published_at')
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
    readonly_fields = ('created_at', 'updated_at')

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
    readonly_fields = ('lesson', 'is_completed', 'completed_at', 'last_position_seconds', 'last_accessed_at')
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
    readonly_fields = ('enrolled_at', 'progress_percentage_display')
    inlines = [LessonProgressInline]

    fieldsets = (
        ("Apprenant & Formation", {
            'fields': ('user', 'course', 'order', 'status', 'source')
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
    readonly_fields = ('enrollment', 'quiz', 'score', 'passed', 'attempt_number', 'submitted_at')

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

