import uuid
from decimal import Decimal
from django.conf import settings
from django.db import models
from django.urls import reverse
from django.utils import timezone
from django.utils.text import slugify
from django.core.validators import MinValueValidator, MaxValueValidator
from django.core.files.uploadedfile import UploadedFile
from cloudinary.models import CloudinaryField
from .image_utils import validate_course_cover_image, optimize_course_cover_image


class CourseCategory(models.Model):
    """Catégories spécifiques aux formations (ex: Méditation, Lithothérapie, Énergétique)."""
    name = models.CharField("Nom de la catégorie", max_length=150)
    slug = models.SlugField("Slug", max_length=150, unique=True, blank=True)
    description = models.TextField("Description", blank=True)
    icon = models.CharField("Icône FontAwesome", max_length=50, blank=True, default="fa-graduation-cap")
    order = models.PositiveIntegerField("Ordre d'affichage", default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Catégorie de formation"
        verbose_name_plural = "Catégories de formation"
        ordering = ['order', 'name']

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)


class Course(models.Model):
    """Formation complète proposée sur Venus Luna."""

    class Level(models.TextChoices):
        BEGINNER = 'beginner', 'Débutant'
        INTERMEDIATE = 'intermediate', 'Intermédiaire'
        ADVANCED = 'advanced', 'Avancé'
        ALL_LEVELS = 'all_levels', 'Tous niveaux'

    class Status(models.TextChoices):
        DRAFT = 'draft', 'Brouillon'
        PUBLISHED = 'published', 'Publiée'
        ARCHIVED = 'archived', 'Archivée'

    title = models.CharField("Titre", max_length=255)
    slug = models.SlugField("Slug", max_length=255, unique=True, blank=True)
    short_description = models.CharField("Description courte", max_length=350, blank=True)
    description = models.TextField("Description détaillée")
    cover_image = CloudinaryField('cover_image', folder='courses', blank=True, null=True)

    category = models.ForeignKey(
        CourseCategory,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='courses',
        verbose_name="Catégorie",
    )
    instructor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='taught_courses',
        verbose_name="Formateur",
    )

    level = models.CharField("Niveau", max_length=20, choices=Level.choices, default=Level.ALL_LEVELS)
    estimated_duration_hours = models.DecimalField("Durée estimée (heures)", max_digits=5, decimal_places=1, default=2.0)

    is_free = models.BooleanField("Formation gratuite", default=False)
    price = models.DecimalField("Prix actuel (FCFA)", max_digits=10, decimal_places=0, default=0)
    old_price = models.DecimalField("Prix barré (FCFA)", max_digits=10, decimal_places=0, null=True, blank=True)

    status = models.CharField("Statut", max_length=20, choices=Status.choices, default=Status.DRAFT)
    published_at = models.DateTimeField("Date de publication", null=True, blank=True)

    # Révision pédagogique actuellement publiée (seule source de contenu pour les nouveaux
    # apprenants). Modifiée exclusivement par apps.courses.revisions.publish_revision().
    # Intégrité (même formation, statut APPROVED) garantie en base sur PostgreSQL.
    published_revision = models.ForeignKey(
        'CourseRevision',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='+',
        editable=False,
        verbose_name="Révision publiée",
    )

    objectives = models.TextField("Objectifs pédagogiques", blank=True, help_text="Un objectif par ligne")
    prerequisites = models.TextField("Prérequis", blank=True, help_text="Un prérequis par ligne")
    syllabus = models.TextField("Programme synthétique", blank=True)

    certificate_enabled = models.BooleanField("Délivre un certificat de fin de formation", default=True)
    certificate_passing_score = models.PositiveIntegerField(
        "Score minimum requis pour la certification (%)",
        default=80,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Formation"
        verbose_name_plural = "Formations"
        ordering = ['-published_at', '-created_at']

    def __str__(self):
        return self.title

    def clean(self):
        super().clean()
        if self.cover_image and isinstance(self.cover_image, UploadedFile):
            validate_course_cover_image(self.cover_image)

    def save(self, *args, **kwargs):
        if not self.slug:
            base = slugify(self.title)[:200]
            slug = base
            counter = 1
            while Course.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                slug = f"{base}-{counter}"
                counter += 1
            self.slug = slug

        if self.is_free:
            self.price = Decimal("0")

        if self.status == self.Status.PUBLISHED and not self.published_at:
            self.published_at = timezone.now()

        # Optimisation automatique de l'image de couverture avant envoi vers Cloudinary
        if self.cover_image and isinstance(self.cover_image, UploadedFile):
            self.cover_image = optimize_course_cover_image(self.cover_image)

        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse('courses:course_detail', kwargs={'slug': self.slug})

    def get_published_content(self):
        """Contenu de la révision publiée (None si aucune révision n'est publiée)."""
        if not self.published_revision_id:
            return None
        return self.published_revision.get_content(course=self)

    def get_working_copy_content(self):
        """Aperçu de la copie de travail (tables vivantes) — réservé au formateur et au staff."""
        from .content import CourseContent, build_snapshot
        return CourseContent(self, build_snapshot(self), revision=None)

    @property
    def is_available_for_learners(self) -> bool:
        return self.status == self.Status.PUBLISHED and self.published_revision_id is not None

    @property
    def total_lessons_count(self) -> int:
        """Nombre de leçons de la révision publiée (copie de travail si aucune révision publiée)."""
        content = self.get_published_content()
        if content is not None:
            return content.total_lessons
        return Lesson.objects.filter(module__course=self, is_published=True).count()

    @property
    def total_duration_minutes(self) -> int:
        content = self.get_published_content()
        if content is not None:
            return content.total_duration_minutes
        agg = Lesson.objects.filter(module__course=self, is_published=True).aggregate(models.Sum('duration_minutes'))
        return agg['duration_minutes__sum'] or 0

    def get_objectives_list(self):
        if not self.objectives:
            return []
        return [line.strip().lstrip('-•* ') for line in self.objectives.splitlines() if line.strip()]

    def get_prerequisites_list(self):
        if not self.prerequisites:
            return []
        return [line.strip().lstrip('-•* ') for line in self.prerequisites.splitlines() if line.strip()]


class CourseModule(models.Model):
    """Module thématique au sein d'une formation."""
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='modules', verbose_name="Formation")
    title = models.CharField("Titre du module", max_length=255)
    description = models.TextField("Description", blank=True)
    order = models.PositiveIntegerField("Ordre d'affichage", default=0)
    is_published = models.BooleanField("Publié", default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Module de formation"
        verbose_name_plural = "Modules de formation"
        ordering = ['order', 'created_at']

    def __str__(self):
        return f"{self.course.title} — Module {self.order + 1} : {self.title}"


class Lesson(models.Model):
    """Leçon individuelle rattachée à un module."""

    class LessonType(models.TextChoices):
        VIDEO = 'video', 'Vidéo'
        TEXT = 'text', 'Texte / Article'
        PDF = 'pdf', 'Document PDF'
        RESOURCE = 'resource', 'Ressources téléchargeables'
        MIXED = 'mixed', 'Contenu mixte'
        QUIZ = 'quiz', 'Quiz d’évaluation'

    module = models.ForeignKey(CourseModule, on_delete=models.CASCADE, related_name='lessons', verbose_name="Module")
    title = models.CharField("Titre de la leçon", max_length=255)
    slug = models.SlugField("Slug", max_length=255, blank=True)
    lesson_type = models.CharField("Type de leçon", max_length=20, choices=LessonType.choices, default=LessonType.VIDEO)
    description = models.TextField("Courte description", blank=True)
    content = models.TextField("Contenu textuel / Notes de cours", blank=True)

    video_url = models.URLField(
        "Lien vidéo (YouTube / Vimeo / Cloudinary)",
        max_length=500,
        blank=True,
        help_text="URL intégrable ou vidéo MP4 / HLS / Vimeo / YouTube",
    )
    attachment_file = models.FileField(
        "Document ou ressource jointe",
        upload_to='courses/attachments/%Y/%m/',
        blank=True,
        null=True,
    )
    attachment_name = models.CharField("Nom de la ressource", max_length=255, blank=True)

    duration_minutes = models.PositiveIntegerField("Durée estimée (minutes)", default=10)
    order = models.PositiveIntegerField("Ordre d'affichage", default=0)

    is_free_preview = models.BooleanField(
        "Aperçu gratuit",
        default=False,
        help_text="Permet aux visiteurs de découvrir cette leçon sans acheter la formation",
    )
    is_published = models.BooleanField("Publiée", default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Leçon"
        verbose_name_plural = "Leçons"
        ordering = ['module__order', 'order', 'created_at']

    def __str__(self):
        return f"{self.module.course.title} — {self.title}"

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.title)[:200]
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse('courses:lesson_detail', kwargs={
            'course_slug': self.module.course.slug,
            'lesson_id': self.id,
        })

    def get_previous_lesson(self):
        """Retourne la leçon précédente dans la formation."""
        return (
            Lesson.objects.filter(
                module__course=self.module.course,
                is_published=True,
            )
            .filter(
                models.Q(module__order__lt=self.module.order) |
                models.Q(module__order=self.module.order, order__lt=self.order)
            )
            .order_by('-module__order', '-order')
            .first()
        )

    def get_next_lesson(self):
        """Retourne la leçon suivante dans la formation."""
        return (
            Lesson.objects.filter(
                module__course=self.module.course,
                is_published=True,
            )
            .filter(
                models.Q(module__order__gt=self.module.order) |
                models.Q(module__order=self.module.order, order__gt=self.order)
            )
            .order_by('module__order', 'order')
            .first()
        )


class Enrollment(models.Model):
    """Inscription officielle d'un utilisateur à une formation."""

    class Status(models.TextChoices):
        ACTIVE = 'active', 'Actif'
        COMPLETED = 'completed', 'Terminé'
        EXPIRED = 'expired', 'Expiré'
        CANCELLED = 'cancelled', 'Annulé'

    class Source(models.TextChoices):
        FREE = 'free', 'Gratuit'
        CASHPAY = 'cashpay', 'Achat CashPay'
        MANUAL_ADMIN = 'manual_admin', 'Attribution manuelle'

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='enrollments', verbose_name="Apprenant")
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='enrollments', verbose_name="Formation")
    enrolled_at = models.DateTimeField("Date d'inscription", auto_now_add=True)
    status = models.CharField("Statut", max_length=20, choices=Status.choices, default=Status.ACTIVE)
    source = models.CharField("Source", max_length=20, choices=Source.choices, default=Source.FREE)

    order = models.ForeignKey(
        'orders.Order',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='course_enrollments',
        verbose_name="Commande associée",
    )
    expires_at = models.DateTimeField("Date d'expiration", null=True, blank=True)

    last_accessed_lesson = models.ForeignKey(
        Lesson,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='+',
        verbose_name="Dernière leçon consultée",
    )
    last_activity_at = models.DateTimeField("Dernière activité", default=timezone.now)
    completed_at = models.DateTimeField("Date d'achèvement", null=True, blank=True)

    # Révision suivie par l'apprenant. NULL = inscription historique non versionnée
    # (antérieure au versionnement) : le contenu affiché est alors la révision publiée
    # courante, sans que ce rattachement soit enregistré.
    revision = models.ForeignKey(
        'CourseRevision',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='enrollments',
        verbose_name="Révision suivie",
    )

    class Meta:
        verbose_name = "Inscription"
        verbose_name_plural = "Inscriptions"
        unique_together = ('user', 'course')
        ordering = ['-enrolled_at']

    def __str__(self):
        return f"{self.user.username} → {self.course.title} ({self.get_status_display()})"

    def is_active_access(self) -> bool:
        if self.status not in (self.Status.ACTIVE, self.Status.COMPLETED):
            return False
        if self.expires_at and timezone.now() > self.expires_at:
            return False
        return True

    @property
    def is_unversioned_legacy(self) -> bool:
        return self.revision_id is None

    def get_effective_revision(self):
        """Révision servie : celle de l'inscription, sinon (historique) la révision publiée courante."""
        if self.revision_id:
            return self.revision
        if self.course.published_revision_id:
            return self.course.published_revision
        return None

    def get_content(self):
        cache = getattr(self, '_content_cache', None)
        if cache is not None:
            return cache
        revision = self.get_effective_revision()
        content = revision.get_content(course=self.course) if revision else None
        self._content_cache = content
        return content

    def _completed_lesson_ids(self, content):
        return set(
            self.progresses.filter(is_completed=True, lesson_id__in=content.lesson_ids)
            .values_list('lesson_id', flat=True)
        )

    def get_progress_percentage(self) -> int:
        content = self.get_content()
        if content is None or content.total_lessons == 0:
            return 0
        completed = len(self._completed_lesson_ids(content))
        return min(100, int((completed / content.total_lessons) * 100))

    def get_resume_lesson(self):
        """Retourne la dernière leçon consultée ou la première non terminée (dans la révision servie)."""
        content = self.get_content()
        if content is None:
            return None
        if self.last_accessed_lesson_id:
            last = content.get_lesson(self.last_accessed_lesson_id)
            if last is not None:
                return last

        completed_ids = self._completed_lesson_ids(content)
        for lesson in content.lessons:
            if lesson.id not in completed_ids:
                return lesson
        return content.first_lesson()

    def check_and_update_completion(self):
        """Vérifie si toutes les leçons de la révision servie sont achevées."""
        content = self.get_content()
        total = content.total_lessons if content is not None else 0
        if total > 0:
            completed = len(self._completed_lesson_ids(content))
            if completed >= total:
                if self.status != self.Status.COMPLETED:
                    self.status = self.Status.COMPLETED
                    self.completed_at = timezone.now()
                    self.save(update_fields=['status', 'completed_at'])
                return True
        return False


class LessonProgress(models.Model):
    """Enregistrement du suivi de progression d'une leçon pour une inscription donnée."""
    enrollment = models.ForeignKey(Enrollment, on_delete=models.CASCADE, related_name='progresses', verbose_name="Inscription")
    # PROTECT : la suppression d'une leçon ne doit pas effacer l'historique des apprenants
    # (dépublier la leçon via is_published=False à la place).
    lesson = models.ForeignKey(Lesson, on_delete=models.PROTECT, related_name='progresses', verbose_name="Leçon")
    # Révision dans laquelle la progression a été enregistrée (NULL = donnée historique non versionnée).
    revision = models.ForeignKey(
        'CourseRevision', on_delete=models.PROTECT, null=True, blank=True,
        related_name='lesson_progresses', verbose_name="Révision",
    )
    is_completed = models.BooleanField("Terminée", default=False)
    completed_at = models.DateTimeField("Terminée le", null=True, blank=True)
    last_position_seconds = models.PositiveIntegerField("Dernière position vidéo (secondes)", default=0)
    last_accessed_at = models.DateTimeField("Dernière consultation", auto_now=True)

    class Meta:
        verbose_name = "Progression de leçon"
        verbose_name_plural = "Progressions de leçons"
        unique_together = ('enrollment', 'lesson')
        ordering = ['-last_accessed_at']

    def __str__(self):
        return f"{self.enrollment.user.username} - {self.lesson.title} : {'✓' if self.is_completed else 'En cours'}"

    def mark_completed(self):
        if not self.is_completed:
            self.is_completed = True
            self.completed_at = timezone.now()
            self.save(update_fields=['is_completed', 'completed_at', 'last_accessed_at'])
            self.enrollment.last_activity_at = timezone.now()
            self.enrollment.last_accessed_lesson = self.lesson
            self.enrollment.save(update_fields=['last_activity_at', 'last_accessed_lesson'])
            self.enrollment.check_and_update_completion()


class Quiz(models.Model):
    """Quiz d'évaluation associé à une leçon ou à la fin d'un module/cours."""
    lesson = models.OneToOneField(Lesson, on_delete=models.CASCADE, related_name='quiz', verbose_name="Leçon associée")
    title = models.CharField("Titre du quiz", max_length=255)
    description = models.TextField("Instructions et consignes", blank=True)
    passing_score = models.PositiveIntegerField(
        "Score minimum requis (%)",
        default=80,
        validators=[MinValueValidator(1), MaxValueValidator(100)],
    )
    max_attempts = models.PositiveIntegerField(
        "Nombre maximal de tentatives",
        default=0,
        help_text="0 pour un nombre illimité de tentatives",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Quiz"
        verbose_name_plural = "Quiz"

    def __str__(self):
        return f"Quiz : {self.title} ({self.lesson.module.course.title})"

    @property
    def total_questions_count(self) -> int:
        return self.questions.count()


class QuizQuestion(models.Model):
    """Question d'un quiz."""

    class QuestionType(models.TextChoices):
        SINGLE = 'single', 'Choix unique'
        MULTIPLE = 'multiple', 'Choix multiples'

    quiz = models.ForeignKey(Quiz, on_delete=models.CASCADE, related_name='questions', verbose_name="Quiz")
    question_text = models.TextField("Énoncé de la question")
    question_type = models.CharField("Type de question", max_length=20, choices=QuestionType.choices, default=QuestionType.SINGLE)
    order = models.PositiveIntegerField("Ordre d'affichage", default=0)
    points = models.PositiveIntegerField("Nombre de points", default=1)
    explanation = models.TextField("Explication pédagogique (affichée après validation)", blank=True)

    class Meta:
        verbose_name = "Question de quiz"
        verbose_name_plural = "Questions de quiz"
        ordering = ['order', 'id']

    def __str__(self):
        return f"Q{self.order + 1}: {self.question_text[:60]}"


class QuizAnswerOption(models.Model):
    """Option de réponse pour une question de quiz."""
    question = models.ForeignKey(QuizQuestion, on_delete=models.CASCADE, related_name='options', verbose_name="Question")
    option_text = models.CharField("Texte de l'option", max_length=500)
    is_correct = models.BooleanField("Est une bonne réponse", default=False)
    order = models.PositiveIntegerField("Ordre", default=0)

    class Meta:
        verbose_name = "Option de réponse"
        verbose_name_plural = "Options de réponse"
        ordering = ['order', 'id']

    def __str__(self):
        return f"{self.option_text} {'(Correcte)' if self.is_correct else ''}"


class QuizAttempt(models.Model):
    """Enregistrement d'une tentative de passage d'un quiz par un apprenant."""
    enrollment = models.ForeignKey(Enrollment, on_delete=models.CASCADE, related_name='quiz_attempts', verbose_name="Inscription")
    # PROTECT : les tentatives passées ne doivent jamais disparaître avec le quiz vivant.
    quiz = models.ForeignKey(Quiz, on_delete=models.PROTECT, related_name='attempts', verbose_name="Quiz")
    score = models.DecimalField("Score obtenu (%)", max_digits=5, decimal_places=2, default=0.00)
    passed = models.BooleanField("Réussi", default=False)
    attempt_number = models.PositiveIntegerField("Numéro de tentative", default=1)
    submitted_at = models.DateTimeField("Date de soumission", auto_now_add=True)
    # Révision évaluée (NULL = tentative historique non versionnée).
    revision = models.ForeignKey(
        'CourseRevision', on_delete=models.PROTECT, null=True, blank=True,
        related_name='quiz_attempts', verbose_name="Révision évaluée",
    )
    # Contexte complet et figé de l'évaluation : questions présentées, options,
    # réponses sélectionnées, bonnes réponses au moment de l'évaluation, règle de
    # notation et points. Vide pour les tentatives historiques (non reconstituables).
    attempt_snapshot = models.JSONField("Contexte figé de la tentative", null=True, blank=True, editable=False)

    @property
    def is_detail_available(self) -> bool:
        return bool(self.attempt_snapshot)

    class Meta:
        verbose_name = "Tentative de quiz"
        verbose_name_plural = "Tentatives de quiz"
        ordering = ['-submitted_at']

    def __str__(self):
        return f"{self.enrollment.user.username} - {self.quiz.title} : {self.score}% ({'Validé' if self.passed else 'Échoué'})"


class Certificate(models.Model):
    """Certificat officiel de complétion délivré à un apprenant."""
    enrollment = models.OneToOneField(Enrollment, on_delete=models.CASCADE, related_name='certificate', verbose_name="Inscription")
    certificate_code = models.CharField("Code unique de vérification", max_length=64, unique=True, db_index=True)
    issued_at = models.DateTimeField("Délivré le", default=timezone.now)
    pdf_file = models.FileField("Document PDF du certificat", upload_to='certificates/%Y/%m/', blank=True, null=True)
    is_valid = models.BooleanField("Certificat valide", default=True)
    revocation_reason = models.CharField("Motif de révocation", max_length=255, blank=True)

    class Meta:
        verbose_name = "Certificat"
        verbose_name_plural = "Certificats"
        ordering = ['-issued_at']

    def __str__(self):
        return f"Certificat #{self.certificate_code} — {self.enrollment.user.get_full_name() or self.enrollment.user.username}"

    def save(self, *args, **kwargs):
        if not self.certificate_code:
            self.certificate_code = self.generate_code()
        super().save(*args, **kwargs)

    @classmethod
    def generate_code(cls) -> str:
        code = f"VL-{uuid.uuid4().hex[:12].upper()}"
        while cls.objects.filter(certificate_code=code).exists():
            code = f"VL-{uuid.uuid4().hex[:12].upper()}"
        return code

    def get_verification_url(self):
        return reverse('courses:verify_certificate', kwargs={'code': self.certificate_code})



# =============================================================================
# VERSIONNEMENT PÉDAGOGIQUE
# =============================================================================

class CourseRevisionImmutableError(Exception):
    """Tentative de modification d'une révision figée."""


class CourseRevision(models.Model):
    """
    Révision pédagogique d'une formation.

    Cycle de vie : DRAFT → SUBMITTED → APPROVED | REJECTED ; DRAFT/SUBMITTED → WITHDRAWN.
    - DRAFT : le contenu vit dans les tables de travail (snapshot vide).
    - SUBMITTED : snapshot figé ; seule la décision de revue peut changer.
    - APPROVED / REJECTED / WITHDRAWN : états terminaux, immuables.
    La publication est distincte : elle consiste à pointer Course.published_revision
    vers une révision APPROVED (published_at ne peut être renseigné qu'une seule fois).
    """

    class Status(models.TextChoices):
        DRAFT = 'DRAFT', 'Brouillon'
        SUBMITTED = 'SUBMITTED', 'Soumise'
        APPROVED = 'APPROVED', 'Approuvée'
        REJECTED = 'REJECTED', 'Rejetée'
        WITHDRAWN = 'WITHDRAWN', 'Retirée'

    OPEN_STATUSES = ('DRAFT', 'SUBMITTED')
    TERMINAL_STATUSES = ('APPROVED', 'REJECTED', 'WITHDRAWN')

    course = models.ForeignKey(Course, on_delete=models.PROTECT, related_name='revisions', verbose_name="Formation")
    revision_number = models.PositiveIntegerField("Numéro de révision")
    status = models.CharField("Statut", max_length=12, choices=Status.choices, default=Status.DRAFT)

    snapshot = models.JSONField("Snapshot pédagogique", null=True, blank=True, editable=False)
    content_hash = models.CharField("Empreinte SHA-256 du snapshot", max_length=64, blank=True, editable=False)

    change_summary = models.TextField("Résumé des modifications", blank=True)
    review_notes = models.TextField("Notes de revue / motif de rejet", blank=True)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='created_course_revisions', verbose_name="Créée par",
    )
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='reviewed_course_revisions', verbose_name="Revue par",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    submitted_at = models.DateTimeField("Soumise le", null=True, blank=True)
    reviewed_at = models.DateTimeField("Revue le", null=True, blank=True)
    approved_at = models.DateTimeField("Approuvée le", null=True, blank=True)
    published_at = models.DateTimeField("Première publication le", null=True, blank=True)

    class Meta:
        verbose_name = "Révision de formation"
        verbose_name_plural = "Révisions de formation"
        ordering = ['course', '-revision_number']
        permissions = [
            ('review_courserevision', "Peut approuver ou rejeter une révision de formation"),
            ('publish_courserevision', "Peut publier une révision de formation"),
        ]
        constraints = [
            models.UniqueConstraint(fields=['course', 'revision_number'], name='uniq_courserevision_number'),
            # Cible de la clé étrangère composite Course(id, published_revision_id) (PostgreSQL).
            models.UniqueConstraint(fields=['course', 'id'], name='uniq_courserevision_course_id'),
            # Une seule révision ouverte (DRAFT ou SUBMITTED) par formation : la copie de
            # travail étant unique, deux brouillons concurrents n'auraient pas de sens.
            models.UniqueConstraint(
                fields=['course'],
                condition=models.Q(status__in=['DRAFT', 'SUBMITTED']),
                name='uniq_courserevision_open_per_course',
            ),
            # Un brouillon n'a pas de snapshot ; une révision soumise, approuvée ou rejetée en a un.
            models.CheckConstraint(
                condition=(
                    models.Q(status='DRAFT', snapshot__isnull=True)
                    | models.Q(status__in=['SUBMITTED', 'APPROVED', 'REJECTED'], snapshot__isnull=False)
                    | models.Q(status='WITHDRAWN')
                ),
                name='chk_courserevision_snapshot_state',
            ),
            models.CheckConstraint(
                condition=models.Q(published_at__isnull=True) | models.Q(status='APPROVED'),
                name='chk_courserevision_published_is_approved',
            ),
        ]

    def __str__(self):
        return f"{self.course.title} — révision {self.revision_number} ({self.get_status_display()})"

    # -- Immutabilité applicative (doublée par un trigger PostgreSQL) -------------

    _IMMUTABLE_WHEN_SUBMITTED = ('course_id', 'revision_number', 'snapshot', 'content_hash',
                                 'change_summary', 'created_by_id', 'submitted_at', 'created_at')
    _IMMUTABLE_WHEN_TERMINAL = _IMMUTABLE_WHEN_SUBMITTED + ('status', 'review_notes', 'reviewed_by_id',
                                                           'reviewed_at', 'approved_at')
    _ALLOWED_FROM_SUBMITTED = ('SUBMITTED', 'APPROVED', 'REJECTED', 'WITHDRAWN')

    def _check_immutability(self, previous):
        old_status = previous.status
        if old_status == self.Status.DRAFT:
            return
        fields = (self._IMMUTABLE_WHEN_TERMINAL if old_status in self.TERMINAL_STATUSES
                  else self._IMMUTABLE_WHEN_SUBMITTED)
        for field in fields:
            if getattr(previous, field) != getattr(self, field):
                raise CourseRevisionImmutableError(
                    f"La révision {previous.pk} ({old_status}) est figée : "
                    f"le champ '{field}' ne peut pas être modifié."
                )
        if old_status == self.Status.SUBMITTED and self.status not in self._ALLOWED_FROM_SUBMITTED:
            raise CourseRevisionImmutableError("Une révision soumise ne peut pas revenir à l'état brouillon.")
        if previous.published_at is not None and previous.published_at != self.published_at:
            raise CourseRevisionImmutableError("La date de première publication ne peut pas être modifiée.")

    def save(self, *args, **kwargs):
        if self.pk:
            previous = CourseRevision.objects.filter(pk=self.pk).first()
            if previous is not None:
                self._check_immutability(previous)
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        # Contrôle sur l'état en base (l'instance en mémoire peut avoir été altérée).
        db_status = CourseRevision.objects.filter(pk=self.pk).values_list('status', flat=True).first()
        if db_status != self.Status.DRAFT:
            raise CourseRevisionImmutableError("Seule une révision brouillon peut être supprimée.")
        return super().delete(*args, **kwargs)

    # -- Lecture -------------------------------------------------------------------

    @property
    def is_frozen(self) -> bool:
        return self.status != self.Status.DRAFT

    def get_content(self, course=None):
        """Contenu figé de la révision (None pour un brouillon : utiliser la copie de travail)."""
        if self.snapshot is None:
            return None
        cache = getattr(self, '_content_cache', None)
        if cache is None:
            from .content import CourseContent
            cache = CourseContent(course or self.course, self.snapshot, revision=self)
            self._content_cache = cache
        return cache


class CourseRevisionEvent(models.Model):
    """Journal append-only des actions de workflow sur une révision (traçabilité administrative)."""

    class Action(models.TextChoices):
        CREATED = 'CREATED', 'Création du brouillon'
        SUBMITTED = 'SUBMITTED', 'Soumission'
        APPROVED = 'APPROVED', 'Approbation'
        REJECTED = 'REJECTED', 'Rejet'
        WITHDRAWN = 'WITHDRAWN', 'Retrait'
        PUBLISHED = 'PUBLISHED', 'Publication'
        INITIAL_IMPORT = 'INITIAL_IMPORT', 'Import initial (migration)'

    revision = models.ForeignKey(CourseRevision, on_delete=models.PROTECT, related_name='events', verbose_name="Révision")
    action = models.CharField("Action", max_length=20, choices=Action.choices)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='+', verbose_name="Auteur",
    )
    note = models.TextField("Note", blank=True)
    previous_published_revision = models.ForeignKey(
        CourseRevision, on_delete=models.PROTECT, null=True, blank=True, related_name='+',
        verbose_name="Révision publiée remplacée",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Événement de révision"
        verbose_name_plural = "Historique des révisions"
        ordering = ['-created_at', '-id']

    def __str__(self):
        return f"{self.get_action_display()} — {self.revision}"


# =============================================================================
# DROITS D'ACCÈS
# =============================================================================

class AccessGrant(models.Model):
    """
    Droit d'accès précis et traçable à une formation, lié à sa provenance.

    - Enrollment reste le dossier pédagogique unique (user, course) : progression,
      tentatives, certificat.
    - AccessGrant conserve l'historique des droits : un droit par ligne d'achat
      (réachat = nouveau droit, l'ancien n'est jamais réutilisé ni écrasé),
      révocation sans suppression.
    """

    class Source(models.TextChoices):
        CASHPAY = 'cashpay', 'Achat CashPay'
        FREE = 'free', 'Gratuit'
        MANUAL_ADMIN = 'manual_admin', 'Attribution manuelle'

    class Status(models.TextChoices):
        ACTIVE = 'active', 'Actif'
        REVOKED = 'revoked', 'Révoqué'

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='access_grants', verbose_name="Apprenant")
    course = models.ForeignKey(Course, on_delete=models.PROTECT, related_name='access_grants', verbose_name="Formation")
    revision = models.ForeignKey(CourseRevision, on_delete=models.PROTECT, related_name='access_grants', verbose_name="Révision attribuée")
    enrollment = models.ForeignKey(Enrollment, on_delete=models.CASCADE, related_name='access_grants', verbose_name="Inscription")
    order_item = models.OneToOneField(
        'orders.OrderItem', on_delete=models.PROTECT, null=True, blank=True,
        related_name='access_grant', verbose_name="Ligne de commande d'origine",
    )
    source = models.CharField("Source", max_length=20, choices=Source.choices)
    status = models.CharField("Statut", max_length=10, choices=Status.choices, default=Status.ACTIVE)

    granted_at = models.DateTimeField("Attribué le", default=timezone.now)
    granted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='+', verbose_name="Attribué par",
    )
    revoked_at = models.DateTimeField("Révoqué le", null=True, blank=True)
    revoked_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='+', verbose_name="Révoqué par",
    )
    revocation_reason = models.CharField("Motif de révocation", max_length=255, blank=True)

    class Meta:
        verbose_name = "Droit d'accès"
        verbose_name_plural = "Droits d'accès"
        ordering = ['-granted_at']
        constraints = [
            # Achat : exactement une ligne de commande par droit CashPay ; aucune pour les autres sources.
            models.CheckConstraint(
                condition=(models.Q(source='cashpay', order_item__isnull=False)
                           | (~models.Q(source='cashpay') & models.Q(order_item__isnull=True))),
                name='chk_accessgrant_source_order_item',
            ),
            # Un seul droit gratuit / manuel actif à la fois par apprenant, formation et source.
            models.UniqueConstraint(
                fields=['user', 'course', 'source'],
                condition=models.Q(status='active') & ~models.Q(source='cashpay'),
                name='uniq_accessgrant_active_nonpurchase',
            ),
            models.CheckConstraint(
                condition=(models.Q(status='active', revoked_at__isnull=True)
                           | models.Q(status='revoked', revoked_at__isnull=False)),
                name='chk_accessgrant_revocation_state',
            ),
        ]

    def __str__(self):
        return f"{self.user} → {self.course} [{self.get_source_display()} · {self.get_status_display()}]"
