from django.db.models.signals import post_save
from django.dispatch import receiver
from django.core.files.base import ContentFile
from django.db.models import F
from django.db import transaction
from .models import Order
from .utils import generate_order_pdf
from apps.products.models import StockMovement
import logging

logger = logging.getLogger(__name__)


def _record_stock_movement(product, quantity, movement_type, order=None, user=None, comment=""):
    """Crée un enregistrement de mouvement de stock (sans lever d'exception bloquante)."""
    try:
        StockMovement.objects.create(
            product=product,
            quantity=quantity,
            movement_type=movement_type,
            order=order,
            user=user,
            comment=comment,
        )
    except Exception as e:
        logger.error("Erreur enregistrement mouvement de stock pour %s: %s", product, e)


@receiver(post_save, sender=Order)
def handle_order_automation(sender, instance, created, **kwargs):
    """
    Gère les automations de stock et de PDF de manière atomique.
    Déclenché après le paiement réussi (via Webhook CashPay).
    """
    order_user = instance.user

    # 1. LOGIQUE : COMMANDE PAYÉE (Déduction du stock + PDF + mouvement SALE)
    if instance.status == 'paid' and not instance.stock_updated:
        try:
            # A. Génération du PDF si absent
            if not instance.receipt:
                pdf_content = generate_order_pdf(instance)
                if pdf_content:
                    filename = f"recu_venus_luna_{instance.id}.pdf"
                    instance.receipt.save(filename, ContentFile(pdf_content), save=False)

            # B. Mise à jour des stocks (Utilisation de F + transaction pour la sécurité)
            with transaction.atomic():
                for item in instance.items.all():
                    if item.product:
                        # Verrouille la ligne pour éviter de passer sous zéro
                        product = item.product.__class__.objects.select_for_update().get(pk=item.product.pk)
                        # Empêche tout stock négatif
                        if product.stock is not None and product.stock < item.quantity:
                            raise ValueError(
                                f"Stock insuffisant pour '{product.name}' (commande #{instance.id}). Stock: {product.stock}, requis: {item.quantity}"
                            )
                        ProductObj = item.product.__class__
                        ProductObj.objects.filter(pk=product.pk).update(stock=F('stock') - item.quantity)
                        # Enregistre le mouvement de vente
                        _record_stock_movement(
                            product,
                            -item.quantity,
                            StockMovement.MovementType.SALE,
                            order=instance,
                            user=order_user,
                            comment=f"Vente - commande #{instance.id}",
                        )

            # C. Validation de l'automation
            Order.objects.filter(id=instance.id).update(stock_updated=True)

            # On sauvegarde le champ receipt séparément car update() ne gère pas bien les fichiers
            if instance.receipt:
                instance.save(update_fields=['receipt'])

            # D. Activation automatique et sécurisée des inscriptions aux formations achetées
            if instance.user:
                try:
                    from apps.courses.models import Enrollment
                    for item in instance.items.all():
                        if item.course:
                            enrollment, was_created = Enrollment.objects.get_or_create(
                                user=instance.user,
                                course=item.course,
                                defaults={
                                    'status': Enrollment.Status.ACTIVE,
                                    'source': Enrollment.Source.CASHPAY,
                                    'order': instance,
                                }
                            )
                            if not was_created and enrollment.status != Enrollment.Status.ACTIVE:
                                enrollment.status = Enrollment.Status.ACTIVE
                                enrollment.order = instance
                                enrollment.save(update_fields=['status', 'order'])
                            logger.info(f"SUCCESS: Inscription activée pour {instance.user.username} sur {item.course.title} (commande #{instance.id})")
                except Exception as enroll_err:
                    logger.error(f"Erreur lors de l'activation de la formation pour la commande #{instance.id}: {enroll_err}")

            logger.info(f"SUCCESS: Stock déduit et PDF généré pour la commande #{instance.id}")

        except Exception as e:
            logger.error(f"ERROR: Echec de l'automation pour la commande #{instance.id}: {e}")

    # 2. LOGIQUE : ANNULATION OU REMBOURSEMENT (Ré-incrémentation du stock physique)
    elif instance.status in ('cancelled', 'refunded') and instance.stock_updated:
        try:
            movement_type = StockMovement.MovementType.CANCEL if instance.status == 'cancelled' else StockMovement.MovementType.REFUND
            with transaction.atomic():
                for item in instance.items.all():
                    if item.product:
                        product = item.product.__class__.objects.select_for_update().get(pk=item.product.pk)
                        ProductObj = item.product.__class__
                        ProductObj.objects.filter(pk=product.pk).update(stock=F('stock') + item.quantity)
                        _record_stock_movement(
                            product,
                            item.quantity,
                            movement_type,
                            order=instance,
                            user=order_user,
                            comment=f"{'Annulation' if instance.status == 'cancelled' else 'Remboursement'} - commande #{instance.id}",
                        )

            Order.objects.filter(id=instance.id).update(stock_updated=False)

            logger.info(f"{instance.get_status_display().upper()}: Commande #{instance.id}, stock rendu.")

        except Exception as e:
            logger.error(f"ERROR: Echec du retour de stock pour #{instance.id}: {e}")

    # 3. LOGIQUE : ANNULATION / REMBOURSEMENT — Désactivation des accès aux formations
    #    (indépendante du stock_updated car les formations numériques n'ont pas de stock physique)
    if instance.status in ('cancelled', 'refunded') and instance.user:
        try:
            from apps.courses.models import Enrollment
            for item in instance.items.all():
                if item.course:
                    Enrollment.objects.filter(
                        user=instance.user,
                        course=item.course,
                        order=instance,
                    ).update(status=Enrollment.Status.CANCELLED)
                    logger.info(f"Inscription désactivée suite à annulation/remboursement pour {instance.user.username} sur {item.course.title}")
        except Exception as enroll_cancel_err:
            logger.error(f"Erreur lors de la désactivation de formation #{instance.id}: {enroll_cancel_err}")
