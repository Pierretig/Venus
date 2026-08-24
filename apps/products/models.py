from decimal import Decimal
from django.conf import settings
from django.db import models
from django.urls import reverse
from django.utils.text import slugify
from django.utils import timezone
from datetime import timedelta
from django.contrib.auth.models import User
from django.core.validators import MinValueValidator, MaxValueValidator
from cloudinary.models import CloudinaryField


def upload_to_product_path(instance, filename):
    return f'products/{instance.__class__.__name__.lower()}/'


class Category(models.Model):
    name = models.CharField("Nom", max_length=200)
    slug = models.SlugField("Slug", max_length=200, unique=True, blank=True)
    description = models.TextField("Description", blank=True)
    order = models.PositiveIntegerField("Ordre", default=0)
    parent = models.ForeignKey(
        'self',
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name='subcategories',
        verbose_name="Catégorie parente"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Catégorie"
        verbose_name_plural = "Catégories"
        ordering = ['order', 'name']

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    def get_descendants(self, include_self=True):
        """Récupère toutes les sous-catégories récursivement."""
        descendants = self.subcategories.all()
        for child in self.subcategories.all():
            descendants |= child.get_descendants()
        if include_self:
            descendants = descendants | self.__class__.objects.filter(pk=self.pk)
        return descendants

    @property
    def display_name(self):
        """Nom avec indent pour hiérarchie."""
        if self.parent:
            return f"{'--' * self.get_depth()} {self.name}"
        return self.name

    def get_depth(self):
        """Profondeur hiérarchique."""
        depth = 0
        cat = self
        while cat.parent:
            depth += 1
            cat = cat.parent
        return depth

    def get_absolute_url(self):
        return reverse('products:category_detail', args=[self.slug])


class Product(models.Model):
    category = models.ForeignKey(Category, related_name='products', on_delete=models.SET_NULL, null=True, blank=True)
    name = models.CharField("Nom", max_length=255)
    slug = models.SlugField("Slug", max_length=255, unique=True, blank=True)
    short_description = models.TextField("Courte description", max_length=500, blank=True)
    description = models.TextField("Description complète", blank=True)

    # Prix adaptés au FCFA
    price = models.DecimalField("Prix actuel (FCFA)", max_digits=10, decimal_places=0, default=0)
    old_price = models.DecimalField("Prix barré (FCFA)", max_digits=10, decimal_places=0, null=True, blank=True)

    is_active = models.BooleanField("Publié / Disponible", default=True)
    stock = models.IntegerField("Stock", default=0)
    featured = models.BooleanField("Mis en avant", default=False)
    restocking_date = models.DateField("Date de réapprovisionnement estimée", null=True, blank=True)
    low_stock_threshold = models.PositiveIntegerField("Seuil d'alerte stock faible", default=5)
    low_stock_alert_sent = models.BooleanField("Alerte stock faible envoyée", default=False)
    
    # Cache des notes
    average_rating = models.DecimalField("Note moyenne", max_digits=3, decimal_places=2, default=0.00)
    total_reviews = models.PositiveIntegerField("Nombre total d'avis", default=0)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Produit"
        verbose_name_plural = "Produits"
        ordering = ['-featured', '-created_at']
        constraints = [
            models.CheckConstraint(condition=models.Q(stock__gte=0), name='product_stock_non_negative')
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._original_stock = self.stock

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse('products:product_detail', args=[self.slug])

    def get_available_stock(self, exclude_session_key=None):
        """
        Calcule le stock disponible en excluant les réservations actives d'autres sessions.
        """
        now = timezone.now()
        active_reservations = self.reservations.filter(expires_at__gt=now)
        if exclude_session_key:
            active_reservations = active_reservations.exclude(session_key=exclude_session_key)

        reserved_qty = active_reservations.aggregate(models.Sum('quantity'))['quantity__sum'] or 0
        return max(0, self.stock - reserved_qty)

    @property
    def is_out_of_stock(self):
        """True si le produit n'a plus de stock réel disponible à la vente."""
        return self.stock <= 0 or self.get_available_stock() <= 0

    @property
    def is_new(self):
        cutoff = timezone.now() - timedelta(days=getattr(settings, 'NOUVEAU_DUREE_JOURS', 15))
        return self.created_at >= cutoff

    @property
    def is_low_stock(self):
        """True si le stock est sous le seuil configuré (et non nul)."""
        return self.stock > 0 and self.stock <= self.low_stock_threshold

    @property
    def available_stock(self):
        """Stock réellement vendable (stock réel moins réservations actives)."""
        return self.get_available_stock()

    def save(self, *args, **kwargs):
        is_new = self.pk is None
        old_stock = self._original_stock if not is_new else 0

        if not self.slug:
            self.slug = slugify(self.name)

        if self.stock < 0:
            from django.core.exceptions import ValidationError
            raise ValidationError("Le stock ne peut pas être négatif.")

        trigger_alerts = False
        if self.stock <= self.low_stock_threshold and not self.low_stock_alert_sent and self.is_active:
            self.low_stock_alert_sent = True
            trigger_alerts = True
        elif self.stock > self.low_stock_threshold and self.low_stock_alert_sent:
            self.low_stock_alert_sent = False

        super().save(*args, **kwargs)

        # Enregistrement automatique des mouvements de stock si modifié et non loggé ailleurs
        if self.stock != old_stock and not getattr(self, '_stock_movement_logged', False):
            diff = self.stock - old_stock
            mtype = StockMovement.MovementType.SUPPLY if diff > 0 else StockMovement.MovementType.MANUAL
            user = getattr(self, '_current_user', None)
            comment = getattr(self, '_movement_comment', "Modification manuelle du stock")

            StockMovement.objects.create(
                product=self,
                quantity=diff,
                movement_type=mtype,
                user=user,
                comment=comment
            )

        # Déclenchement de l'alerte
        if trigger_alerts:
            from .notifications import trigger_low_stock_alerts
            trigger_low_stock_alerts(self)

        self._original_stock = self.stock


class ProductImage(models.Model):
    product = models.ForeignKey(Product, related_name='images', on_delete=models.CASCADE)
    image = CloudinaryField('product_image', folder='products')
    alt_text = models.CharField("Texte alternatif", max_length=255, blank=True)
    is_main = models.BooleanField("Image principale", default=False)
    order = models.PositiveSmallIntegerField("Ordre", default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Image produit"
        verbose_name_plural = "Images produit"
        ordering = ['order', 'created_at']

    def __str__(self):
        return f"Image de {self.product.name}"


class ProductAuditLog(models.Model):
    """Audit trail pour les actions effectuées sur un produit (admin)."""

    class ActionType(models.TextChoices):
        CREATED = 'CREATED', 'Créé'
        UPDATED = 'UPDATED', 'Mis à jour'
        DELETED = 'DELETED', 'Supprimé'
        STATUS_CHANGED = 'STATUS_CHANGED', 'Changement de statut'
        OTHER = 'OTHER', 'Autre'

    product = models.ForeignKey(
        'Product',
        on_delete=models.CASCADE,
        related_name='audit_logs',
    )
    user = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        related_name='product_audit_logs',
        null=True,
        blank=True,
    )
    action_type = models.CharField(max_length=30, choices=ActionType.choices)
    description = models.TextField(blank=True)
    meta = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Journal d’audit produit"
        verbose_name_plural = "Journaux d’audit produits"
        ordering = ['-created_at']

    def __str__(self):
        u = self.user.username if self.user else 'Système'
        return f"{self.action_type} - {self.product_id} - {u}"


class Wishlist(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='wishlist')
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    added_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Liste de souhaits"
        verbose_name_plural = "Listes de souhaits"
        unique_together = ('user', 'product')

    def __str__(self):
        return f"{self.user.username} - {self.product.name}"


class StockMovement(models.Model):
    class MovementType(models.TextChoices):
        SUPPLY = 'SUPPLY', 'Approvisionnement'
        SALE = 'SALE', 'Vente'
        CANCEL = 'CANCEL', 'Annulation'
        REFUND = 'REFUND', 'Remboursement'
        MANUAL = 'MANUAL', 'Correction manuelle'
        INVENTORY = 'INVENTORY', 'Inventaire'

    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='stock_movements')
    quantity = models.IntegerField("Quantité")
    movement_type = models.CharField("Type de mouvement", max_length=20, choices=MovementType.choices)
    created_at = models.DateTimeField("Date", auto_now_add=True)
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Utilisateur")
    order = models.ForeignKey('orders.Order', on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Commande")
    comment = models.TextField("Commentaire", blank=True)

    class Meta:
        verbose_name = "Mouvement de stock"
        verbose_name_plural = "Mouvements de stock"
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.get_movement_type_display()} - {self.product.name} ({self.quantity})"


class StockReservation(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='reservations')
    session_key = models.CharField(max_length=255, db_index=True)
    quantity = models.PositiveIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(db_index=True)

    class Meta:
        verbose_name = "Réservation de stock"
        verbose_name_plural = "Réservations de stock"

    def is_expired(self):
        return timezone.now() > self.expires_at

    def __str__(self):
        return f"Réservation: {self.product.name} x{self.quantity} (Session {self.session_key[:8]})"


class AdminNotification(models.Model):
    title = models.CharField("Titre", max_length=255)
    message = models.TextField("Message")
    is_read = models.BooleanField("Lu", default=False)
    created_at = models.DateTimeField("Créé le", auto_now_add=True)
    notification_type = models.CharField("Type", max_length=50, default='low_stock')

    class Meta:
        verbose_name = "Notification Admin"
        verbose_name_plural = "Notifications Admin"
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.title} - {'Lu' if self.is_read else 'Non lu'}"


class Review(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='reviews', null=True, blank=True, verbose_name="Produit")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='reviews', verbose_name="Client")
    client_name = models.CharField("Nom ou Pseudonyme", max_length=150, help_text="Nom affiché publiquement")
    rating = models.PositiveSmallIntegerField("Note", validators=[MinValueValidator(1), MaxValueValidator(5)])
    title = models.CharField("Titre de l'avis", max_length=150, blank=True)
    comment = models.TextField("Commentaire")
    created_at = models.DateTimeField("Date de publication", auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    # Modération
    is_approved = models.BooleanField("Approuvé / Public", default=False, db_index=True)
    is_pinned = models.BooleanField("Épinglé", default=False, help_text="Afficher en priorité")
    is_featured = models.BooleanField("Mis en avant sur l'accueil", default=False)
    
    # Achat vérifié
    verified_purchase = models.BooleanField("Achat vérifié", default=False)
    
    # Réponse officielle admin
    admin_reply = models.TextField("Réponse de l'administrateur", blank=True)
    admin_reply_at = models.DateTimeField("Date de réponse", null=True, blank=True)

    class Meta:
        verbose_name = "Avis client"
        verbose_name_plural = "Avis clients"
        ordering = ['-is_pinned', '-created_at']
        unique_together = ('product', 'user')

    def __str__(self):
        product_name = self.product.name if self.product else "Venus Luna"
        return f"{self.client_name} - {product_name} ({self.rating}/5)"
