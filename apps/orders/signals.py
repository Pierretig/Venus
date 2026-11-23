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
    Déclenché après le paiement réussi (via Webhook CashPay, confirmation centralisée ou admin Django).
    """
    order_user = instance.user

    # 1. LOGIQUE : COMMANDE PAYÉE (Déduction du stock + PDF + mouvement SALE)
    if instance.status == 'paid' and not instance.stock_updated:
        try:
            with transaction.atomic():
                locked_order = Order.objects.select_for_update().filter(
                    id=instance.id, status='paid', stock_updated=False
                ).first()
                if locked_order:
                    from .payment_processing import process_order_stock_and_fulfillment
                    process_order_stock_and_fulfillment(locked_order)
                    update_fields = ['stock_updated']
                    if locked_order.receipt:
                        update_fields.append('receipt')
                    # Nettoyer ou clore la note d'échec si présente
                    if locked_order.notes and '[ÉCHEC TRAITEMENT STOCK]' in locked_order.notes:
                        cleaned_lines = [
                            line for line in locked_order.notes.splitlines()
                            if not line.startswith('[ÉCHEC TRAITEMENT STOCK]')
                        ]
                        cleaned_lines.append("[STOCK RÉGULARISÉ AVEC SUCCÈS]")
                        locked_order.notes = "\n".join(cleaned_lines).strip()
                        update_fields.append('notes')
                    locked_order.save(update_fields=update_fields)
                    logger.info("handle_order_automation: Automation exécutée avec succès pour commande #%s", instance.id)
        except Exception as e:
            logger.error("handle_order_automation: Échec de l'automation pour commande #%s: %s", instance.id, e)
            fail_msg = f"[ÉCHEC TRAITEMENT STOCK] {str(e)}"
            # Rendre l'état incomplet identifiable dans les notes sans écraser les notes existantes
            current_notes = Order.objects.filter(id=instance.id).values_list('notes', flat=True).first() or ''
            if fail_msg not in current_notes:
                new_notes = f"{current_notes}\n{fail_msg}".strip() if current_notes else fail_msg
                Order.objects.filter(id=instance.id).update(notes=new_notes)

    # 2. LOGIQUE : ANNULATION OU REMBOURSEMENT (Ré-incrémentation du stock physique)
    elif instance.status in ('cancelled', 'refunded') and instance.stock_updated:
        try:
            movement_type = StockMovement.MovementType.CANCEL if instance.status == 'cancelled' else StockMovement.MovementType.REFUND
            with transaction.atomic():
                locked_order = Order.objects.select_for_update().filter(
                    id=instance.id, stock_updated=True
                ).first()
                if locked_order:
                    for item in locked_order.items.all():
                        if item.product:
                            product = item.product.__class__.objects.select_for_update().get(pk=item.product.pk)
                            ProductObj = item.product.__class__
                            ProductObj.objects.filter(pk=product.pk).update(stock=F('stock') + item.quantity)
                            _record_stock_movement(
                                product,
                                item.quantity,
                                movement_type,
                                order=locked_order,
                                user=order_user,
                                comment=f"{'Annulation' if locked_order.status == 'cancelled' else 'Remboursement'} - commande #{locked_order.id}",
                            )

                    Order.objects.filter(id=locked_order.id).update(stock_updated=False)
                    logger.info(f"{locked_order.get_status_display().upper()}: Commande #{locked_order.id}, stock rendu.")

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
