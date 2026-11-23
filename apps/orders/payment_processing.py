import logging
from decimal import Decimal
from django.db import transaction
from django.db.models import F
from django.core.files.base import ContentFile

from .models import Order
from .utils import generate_order_pdf, send_order_paid_email
from apps.products.models import StockMovement

logger = logging.getLogger(__name__)


class PaymentProcessingError(Exception):
    """Exception de base pour les erreurs de traitement de paiement."""
    pass


class OrderAlreadyPaidError(PaymentProcessingError):
    """Levée quand une tentative de paiement est effectuée sur une commande déjà payée."""
    pass


class InsufficientStockError(PaymentProcessingError):
    """Levée quand le stock disponible est insuffisant pour honorer la commande."""
    pass


class InvalidPaymentAmountError(PaymentProcessingError):
    """Levée quand le montant reçu ne correspond pas au total attendu de la commande."""
    pass


def _record_stock_movement_strict(product, quantity, movement_type, order=None, user=None, comment=""):
    """
    Enregistre un mouvement de stock dans la transaction active.
    Ne masque pas les erreurs de base de données afin de garantir la cohérence transactionnelle.
    """
    return StockMovement.objects.create(
        product=product,
        quantity=quantity,
        movement_type=movement_type,
        order=order,
        user=user,
        comment=comment,
    )


def process_order_stock_and_fulfillment(order):
    """
    Traite la déduction de stock, l'enregistrement des mouvements SALE,
    la génération du reçu PDF et les inscriptions aux cours LMS.

    Garantit un verrouillage déterministe (par product_id croissant) pour éliminer
    tout risque d'interblocage (deadlock) entre commandes concurrentes.
    """
    if order.stock_updated:
        logger.info("Stock déjà mis à jour pour la commande #%s. Opération ignorée.", order.id)
        return False

    order_user = order.user

    # 1. Extraction et regroupement des produits physiques de la commande
    physical_items = [item for item in order.items.select_related('product').all() if item.product_id]

    # Agrégation des quantités requises par product_id (sécurise le cas où un même produit est présent sur plusieurs lignes)
    qty_by_product_id = {}
    for item in physical_items:
        qty_by_product_id[item.product_id] = qty_by_product_id.get(item.product_id, 0) + item.quantity

    # 2. Ordonnancement déterministe strict des verrous par product_id croissant (anti-deadlock)
    sorted_product_ids = sorted(qty_by_product_id.keys())
    locked_products = {}

    for pid in sorted_product_ids:
        # Verrouillage de la ligne produit dans un ordre prévisible
        from apps.products.models import Product
        product = Product.objects.select_for_update().get(pk=pid)
        total_required = qty_by_product_id[pid]
        if product.stock is not None and product.stock < total_required:
            raise InsufficientStockError(
                f"Stock insuffisant pour '{product.name}' (commande #{order.id}). "
                f"Stock actuel: {product.stock}, requis: {total_required}"
            )
        locked_products[pid] = product

    # 3. Déduction atomique du stock physique et création des mouvements SALE
    for item in physical_items:
        product = locked_products[item.product_id]
        ProductObj = product.__class__
        ProductObj.objects.filter(pk=product.pk).update(stock=F('stock') - item.quantity)
        _record_stock_movement_strict(
            product=product,
            quantity=-item.quantity,
            movement_type=StockMovement.MovementType.SALE,
            order=order,
            user=order_user,
            comment=f"Vente - commande #{order.id}",
        )

    order.stock_updated = True

    # 3. Génération du reçu PDF client si absent
    if not order.receipt:
        try:
            pdf_content = generate_order_pdf(order)
            if pdf_content:
                filename = f"recu_venus_luna_{order.id}.pdf"
                order.receipt.save(filename, ContentFile(pdf_content), save=False)
        except Exception as pdf_err:
            logger.error("Erreur génération reçu PDF pour commande #%s: %s", order.id, pdf_err)

    # 4. Activation des inscriptions aux formations numériques associées
    if order.user:
        try:
            from apps.courses.models import Enrollment
            for item in order.items.select_related('course').all():
                if item.course:
                    enrollment, was_created = Enrollment.objects.get_or_create(
                        user=order.user,
                        course=item.course,
                        defaults={
                            'status': Enrollment.Status.ACTIVE,
                            'source': Enrollment.Source.CASHPAY,
                            'order': order,
                        }
                    )
                    if not was_created and enrollment.status != Enrollment.Status.ACTIVE:
                        enrollment.status = Enrollment.Status.ACTIVE
                        enrollment.order = order
                        enrollment.save(update_fields=['status', 'order'])
                    logger.info(
                        "Inscription activée pour %s sur %s (commande #%s)",
                        order.user.username, item.course.title, order.id
                    )
        except Exception as enroll_err:
            logger.error(
                "Erreur lors de l'activation formation pour commande #%s: %s",
                order.id, enroll_err
            )

    return True


def _safe_send_paid_email_post_commit(order_id):
    """
    Envoie l'email de confirmation après la validation effective de la transaction en base.
    """
    try:
        order = Order.objects.get(id=order_id)
        send_order_paid_email(order)
    except Exception as exc:
        logger.error("Erreur lors de l'envoi de l'email post-commit pour commande #%s: %s", order_id, exc)


@transaction.atomic
def confirm_order_payment(
    order_id: int,
    transaction_ref: str = None,
    payment_method: str = None,
    amount_received=None,
    currency: str = None,
    send_email: bool = True,
):
    """
    Point d'entrée unique et centralisé pour la confirmation de paiement d'une commande.

    Garantit l'atomicité et l'idempotence stricte :
    - Verrouille la ligne de commande avec select_for_update() (PostgreSQL row-level lock).
    - Refuse tout traitement si la commande est déjà payée (idempotence).
    - Valide les montants avec Decimal.
    - Effectue la déduction de stock et les mouvements SALE dans la même transaction.
    - Met à jour les statuts de paiement (status='paid', payment_status=True, paygate_tx_id, stock_updated=True).
    - Diffère l'envoi de l'email via transaction.on_commit().

    Retourne : (bool, Order, str)
      - bool : True si la confirmation a été effectuée dans cet appel, False sinon.
      - Order : L'instance Order à jour.
      - str : Raison / code d'état ('confirmed', 'already_paid', 'order_not_found', 'invalid_status').
    """
    try:
        order = Order.objects.select_for_update().get(id=order_id)
    except Order.DoesNotExist:
        logger.error("confirm_order_payment: Commande #%s introuvable.", order_id)
        return False, None, "order_not_found"

    clean_ref = str(transaction_ref).strip()[:100] if transaction_ref else None

    # 1. Vérification d'unicité inter-commandes : la référence ne doit pas être déjà associée à une autre commande
    if clean_ref:
        collision_order = Order.objects.filter(paygate_tx_id=clean_ref).exclude(id=order.id).first()
        if collision_order:
            logger.error(
                "confirm_order_payment: Référence de transaction '%s' déjà associée à la commande #%s",
                clean_ref, collision_order.id
            )
            raise PaymentProcessingError(
                f"Référence de transaction '{clean_ref}' déjà associée à la commande #{collision_order.id}."
            )

    # 2. Vérification de cohérence : une référence existante ne doit jamais être remplacée ou contredite silencieusement
    if clean_ref and order.paygate_tx_id:
        if order.paygate_tx_id != clean_ref:
            logger.error(
                "confirm_order_payment: Incohérence de référence pour commande #%s : existante='%s', reçue='%s'",
                order.id, order.paygate_tx_id, clean_ref
            )
            raise PaymentProcessingError(
                f"Incohérence de référence pour commande #{order.id} : référence existante '{order.paygate_tx_id}' différente de '{clean_ref}'."
            )

    # 3. Idempotence : si la commande est déjà payée, rejeter tout nouveau traitement commercial
    if order.payment_status or order.status == 'paid':
        logger.info("confirm_order_payment: Commande #%s déjà marquée payée. Aucun nouveau traitement.", order.id)
        return False, order, "already_paid"

    # 4. Refuser si la commande est dans un état irréversible (annulée ou remboursée)
    if order.status in ('cancelled', 'refunded'):
        logger.warning(
            "confirm_order_payment: Commande #%s rejetée car son statut actuel est '%s'.",
            order.id, order.status
        )
        return False, order, "invalid_status"

    # 3. Vérification de la devise si explicitement fournie par le prestataire
    if currency:
        clean_currency = str(currency).strip().upper()
        if clean_currency not in ('XOF', 'CFA'):
            logger.error("confirm_order_payment: Devise non supportée pour #%s: %s", order.id, currency)
            raise ValueError(f"Devise non supportée: {currency}")

    # 4. Vérification stricte du montant avec Decimal
    if amount_received is not None:
        try:
            received_decimal = Decimal(str(amount_received).strip())
        except Exception as e:
            logger.error("confirm_order_payment: Format de montant invalide (%s): %s", amount_received, e)
            raise InvalidPaymentAmountError(f"Format de montant invalide: {amount_received}")

        if received_decimal < order.total:
            logger.error(
                "confirm_order_payment: Montant reçu insuffisant pour commande #%s. Reçu: %s, Attendu: %s",
                order.id, received_decimal, order.total
            )
            raise InvalidPaymentAmountError(
                f"Montant insuffisant ({received_decimal} < {order.total})"
            )

    # 5. Traitement commercial unifié du stock et des formations
    if not order.stock_updated:
        process_order_stock_and_fulfillment(order)

    # 6. Mise à jour des statuts financiers et des métadonnées de paiement
    order.status = 'paid'
    order.payment_status = True
    update_fields = ['status', 'payment_status', 'stock_updated', 'updated_at']

    if clean_ref and not order.paygate_tx_id:
        order.paygate_tx_id = clean_ref
        update_fields.append('paygate_tx_id')

    if payment_method and not order.payment_method:
        order.payment_method = str(payment_method)[:50]
        update_fields.append('payment_method')

    if order.receipt:
        update_fields.append('receipt')

    order.save(update_fields=update_fields)

    # 7. Notification client par email (uniquement après validation effective du commit)
    if send_email:
        transaction.on_commit(lambda: _safe_send_paid_email_post_commit(order.id))

    logger.info("confirm_order_payment: Commande #%s confirmée avec succès.", order.id)
    return True, order, "confirmed"
