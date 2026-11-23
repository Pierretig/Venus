from django.conf import settings
from django.db import models
from django.utils import timezone

ORDER_STATUS = (
    ('pending', 'En attente de paiement'),
    ('paid', 'Payé (À préparer)'),
    ('processing', 'En cours de traitement'),
    ('shipped', 'Expédié'),
    ('delivered', 'Livré'),
    ('cancelled', 'Annulé'),
    ('refunded', 'Remboursé'),
)

class Order(models.Model):
    # Existing fields remain unchanged
    # -------------------------------------------------
    # Outbox events will be stored in a separate model (see OutboxEvent)
    # -------------------------------------------------

    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='orders')
    email = models.EmailField("Email client", blank=True)
    status = models.CharField("Statut", max_length=20, choices=ORDER_STATUS, default='pending')
    
    # FCFA : decimal_places=0 est idéal pour éviter les virgules inutiles
    subtotal = models.DecimalField("Sous-total", max_digits=10, decimal_places=0, default=0)
    shipping_price = models.DecimalField("Frais de port", max_digits=10, decimal_places=0, default=0)
    total = models.DecimalField("Total", max_digits=10, decimal_places=0, default=0)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    notes = models.TextField("Notes", blank=True)

    # --- Paiement Bkapay ---
    payment_status = models.BooleanField("Paiement confirmé", default=False)
    paygate_tx_id = models.CharField("ID Transaction Bkapay", max_length=100, blank=True, null=True, unique=True)
    payment_url = models.URLField("Lien de paiement", max_length=500, blank=True, null=True)
    payment_method = models.CharField("Méthode (Moov/TMoney)", max_length=50, blank=True, null=True)
    
    receipt = models.FileField("Reçu PDF", upload_to='receipts/%Y/%m/%d/', blank=True, null=True)
    stock_updated = models.BooleanField("Stock mis à jour", default=False, editable=False)
    # Date de la première confirmation interne valide du paiement. Renseignée une seule
    # fois (jamais auto_now) ; NULL pour les commandes antérieures (date inconnue, non inventée).
    paid_at = models.DateTimeField("Payée le", null=True, blank=True, editable=False)

    class Meta:
        verbose_name = "Commande"
        verbose_name_plural = "Commandes"
        ordering = ['-created_at']

    def __str__(self):
        return f"Commande #{self.id} — {self.get_status_display()}"

    def get_total_cost(self):
        """ Retourne le montant total actuel """
        return self.total

    def recalc_total(self, save=True):
        """ 
        Force le recalcul du sous-total et du total final.
        À appeler dans la vue APRES avoir créé les OrderItems.
        """
        shipping = self.shipping_price or 0
        # On calcule la somme des lignes de produits
        self.subtotal = sum(item.line_total for item in self.items.all())
        self.total = self.subtotal + shipping
        
        if save:
            # On met à jour uniquement les champs financiers pour plus de rapidité
            super().save(update_fields=['subtotal', 'total'])

class OrderItem(models.Model):
    order = models.ForeignKey(Order, related_name='items', on_delete=models.CASCADE)
    product = models.ForeignKey('products.Product', null=True, blank=True, on_delete=models.SET_NULL)
    course = models.ForeignKey('courses.Course', null=True, blank=True, on_delete=models.SET_NULL, related_name='order_items', verbose_name="Formation associée")
    name = models.CharField("Nom du produit", max_length=255)
    price = models.DecimalField("Prix unitaire", max_digits=10, decimal_places=0, null=True, blank=True)
    quantity = models.PositiveIntegerField("Quantité", default=1)
    
    @property
    def line_total(self):
        """ Calcule le prix x quantité pour cette ligne """
        p = self.price or 0
        q = self.quantity or 0
        return p * q

    def get_cost(self):
        return self.line_total

    def __str__(self):
        return f"{self.name} x{self.quantity}"

class ShippingAddress(models.Model):
    order = models.OneToOneField(Order, related_name='shipping_address', on_delete=models.CASCADE)
    full_name = models.CharField("Nom complet", max_length=255)
    phone = models.CharField("Téléphone", max_length=50, blank=True)
    address = models.TextField("Adresse")
    city = models.CharField("Ville", max_length=150, blank=True)
    country = models.CharField("Pays", max_length=100, default="Togo")

    class Meta:
        verbose_name = "Adresse de livraison"
        verbose_name_plural = "Adresses de livraison"

class ShippingZone(models.Model):
    name = models.CharField("Quartier / Zone", max_length=100)

    price = models.DecimalField("Frais de livraison", max_digits=10, decimal_places=0)
    delivery_time = models.CharField("Délai estimé", max_length=100, default="24h")
    class Meta:
        verbose_name = "Zone de livraison"
        verbose_name_plural = "Zones de livraison"
        indexes = [
            models.Index(fields=["price"], name="idx_shippingzone_price"),
        ]

    def __str__(self):
        return f"{self.name} ({self.price} F)"

# -----------------------------------------------------------------------------
# Outbox event model for reliable asynchronous processing
# -----------------------------------------------------------------------------

class OutboxEvent(models.Model):
    class EventType(models.TextChoices):
        PDF_RECEIPT = "PDF_RECEIPT", "PDF Receipt"
        COURSE_ENROLLMENT = "COURSE_ENROLLMENT", "Course Enrollment"
        PAYMENT_EMAIL = "PAYMENT_EMAIL", "Payment Email"

    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        PROCESSING = "PROCESSING", "Processing"
        SUCCESS = "SUCCESS", "Success"
        FAILED = "FAILED", "Failed"

    order = models.ForeignKey('Order', related_name='outbox_events', on_delete=models.CASCADE)
    event_type = models.CharField(max_length=30, choices=EventType.choices)
    # Optional link to a course for enrollment events
    course = models.ForeignKey('courses.Course', null=True, blank=True, on_delete=models.SET_NULL)
    payload = models.JSONField(default=dict, blank=True)
    idempotency_key = models.CharField(max_length=255)
    # Jeton de lease : seul le worker qui détient ce jeton peut clore l'événement.
    lease_token = models.UUIDField(null=True, blank=True, editable=False)

    status = models.CharField(max_length=15, choices=Status.choices, default=Status.PENDING)
    attempts = models.PositiveIntegerField(default=0)
    available_at = models.DateTimeField(default=timezone.now)
    processing_at = models.DateTimeField(null=True, blank=True)
    locked_until = models.DateTimeField(null=True, blank=True)
    last_error = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    processed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["status", "available_at"], name="idx_outbox_status_available"),
            models.Index(fields=["locked_until"], name="idx_outbox_locked_until"),
        ]
        constraints = [
            models.UniqueConstraint(fields=["idempotency_key"], name="uniq_outbox_idempotency_key"),
        ]
        ordering = ["-created_at"]

    def __str__(self):
        return f"OutboxEvent {self.id} – {self.get_event_type_display()} ({self.status})"



# -----------------------------------------------------------------------------
# Capture de la révision achetée et réconciliation des paiements
# -----------------------------------------------------------------------------

class PaymentRevisionLink(models.Model):
    """
    Révision pédagogique exacte capturée pour une ligne de formation achetée, lue dans
    Course.published_revision sous verrou au moment de la première confirmation valide.
    Une ligne d'achat ne peut être liée qu'à une seule révision (OneToOne).
    """

    class Source(models.TextChoices):
        PAYMENT_CONFIRMATION = 'payment_confirmation', 'Confirmation du paiement'
        ADMIN_FULFILLMENT = 'admin_fulfillment', 'Traitement administratif de la commande'
        RECONCILIATION = 'reconciliation', 'Réconciliation manuelle'

    order = models.ForeignKey(Order, on_delete=models.PROTECT, related_name='revision_links', verbose_name="Commande")
    order_item = models.OneToOneField(OrderItem, on_delete=models.PROTECT, related_name='revision_link', verbose_name="Ligne de commande")
    # Copie figée de la formation : OrderItem.course est SET_NULL et modifiable, le lien ne l'est pas.
    course = models.ForeignKey('courses.Course', on_delete=models.PROTECT, related_name='payment_revision_links', verbose_name="Formation")
    course_revision = models.ForeignKey('courses.CourseRevision', on_delete=models.PROTECT, related_name='payment_links', verbose_name="Révision achetée")
    source = models.CharField("Provenance", max_length=30, choices=Source.choices)
    captured_at = models.DateTimeField("Capturée le", default=timezone.now)
    captured_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='+', verbose_name="Capturée par",
    )

    class Meta:
        verbose_name = "Révision achetée"
        verbose_name_plural = "Révisions achetées"
        ordering = ['-captured_at']

    def __str__(self):
        return f"Commande #{self.order_id} · ligne #{self.order_item_id} → révision #{self.course_revision_id}"


class PaymentReconciliation(models.Model):
    """
    Incident de paiement nécessitant une intervention : le prestataire a (peut-être)
    encaissé, mais la confirmation interne n'a pas pu être menée à son terme.
    Un rollback SQL n'annule jamais un paiement externe : ces enregistrements sont créés
    hors de la transaction qui a échoué.
    """

    class Kind(models.TextChoices):
        CONFIRMATION_FAILED = 'confirmation_failed', 'Paiement externe accepté, confirmation interne échouée'
        AMOUNT_MISMATCH = 'amount_mismatch', 'Montant ou devise incohérents'
        AMOUNT_UNVERIFIED = 'amount_unverified', 'Montant non vérifiable'
        PROVIDER_STATE = 'provider_state', 'État prestataire à traiter (Partial, Excess…)'
        PAID_ON_CLOSED_ORDER = 'paid_on_closed_order', 'Paiement reçu sur une commande annulée/remboursée'
        NO_PUBLISHED_REVISION = 'no_published_revision', 'Formation achetée sans révision publiée'
        DUPLICATE_PURCHASE = 'duplicate_purchase', "Formation achetée alors qu'un accès actif existait"

    class Status(models.TextChoices):
        OPEN = 'open', 'À traiter'
        RESOLVED = 'resolved', 'Résolu'

    order = models.ForeignKey(Order, on_delete=models.PROTECT, related_name='reconciliations', verbose_name="Commande")
    order_item = models.ForeignKey(
        OrderItem, on_delete=models.PROTECT, null=True, blank=True,
        related_name='reconciliations', verbose_name="Ligne de commande",
    )
    kind = models.CharField("Type", max_length=30, choices=Kind.choices)
    status = models.CharField("Statut", max_length=10, choices=Status.choices, default=Status.OPEN)
    # Clé de déduplication : une notification répétée ne crée pas de doublon tant que l'incident est ouvert.
    dedup_key = models.CharField(max_length=120, editable=False)
    provider_reference = models.CharField("Référence prestataire", max_length=100, blank=True)
    details = models.JSONField("Détails techniques", default=dict, blank=True)
    occurrences = models.PositiveIntegerField("Occurrences", default=1)
    created_at = models.DateTimeField(auto_now_add=True)
    last_seen_at = models.DateTimeField(default=timezone.now)
    resolved_at = models.DateTimeField(null=True, blank=True)
    resolved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='+', verbose_name="Résolu par",
    )
    resolution_note = models.TextField("Note de résolution", blank=True)

    class Meta:
        verbose_name = "Réconciliation de paiement"
        verbose_name_plural = "Réconciliations de paiement"
        ordering = ['-created_at']
        constraints = [
            models.UniqueConstraint(
                fields=['dedup_key'], condition=models.Q(status='open'),
                name='uniq_reconciliation_open_dedup',
            ),
        ]

    def __str__(self):
        return f"{self.get_kind_display()} — commande #{self.order_id} ({self.get_status_display()})"
