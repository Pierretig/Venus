"""
Confirmation des paiements, capture des révisions achetées et réconciliation.

Ordre global de verrouillage (toutes fonctions confondues) :
    Order  →  Course (id croissant)  →  Product (id croissant)
- confirm_order_payment / process_order_stock_and_fulfillment : Order puis Course puis Product.
- revisions.publish_revision : Course uniquement.
- access.revoke_order_access : Order uniquement (puis lignes AccessGrant/Enrollment).
- CourseRevision n'est jamais verrouillée ici : une révision APPROVED est immuable.
Le verrou sur Course est le point de synchronisation entre la capture du paiement et la
publication administrative : la révision lue est celle publiée au moment du commit.
"""
import logging
from decimal import Decimal, InvalidOperation

from django.db import IntegrityError, transaction
from django.db.models import F
from django.utils import timezone

from .models import Order, OutboxEvent, PaymentReconciliation, PaymentRevisionLink
from apps.products.models import StockMovement

logger = logging.getLogger(__name__)

# CashPay V3 : montants entiers en XOF (documentation intégrateur). Toute autre devise est refusée.
SUPPORTED_CURRENCIES = ('XOF',)


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
    """Levée quand le montant ou la devise reçus ne correspondent pas à la commande."""
    pass


# ==============================================================================
# RÉCONCILIATION
# ==============================================================================

def record_reconciliation(order_id, kind, order_item_id=None, provider_reference='', details=None):
    """
    Enregistre (ou incrémente) un incident de paiement à traiter.
    Appelée hors d'une transaction en échec, elle persiste indépendamment du rollback.
    Appelée dans la transaction de confirmation, elle est atomique avec celle-ci.
    """
    key = f"{kind}:{order_id}:{order_item_id or '-'}"
    details = details or {}
    with transaction.atomic():
        existing = (
            PaymentReconciliation.objects.select_for_update()
            .filter(dedup_key=key, status=PaymentReconciliation.Status.OPEN)
            .first()
        )
        if existing is None:
            try:
                with transaction.atomic():
                    return PaymentReconciliation.objects.create(
                        order_id=order_id,
                        order_item_id=order_item_id,
                        kind=kind,
                        dedup_key=key,
                        provider_reference=(provider_reference or '')[:100],
                        details=details,
                    )
            except IntegrityError:
                existing = PaymentReconciliation.objects.select_for_update().get(
                    dedup_key=key, status=PaymentReconciliation.Status.OPEN
                )
        PaymentReconciliation.objects.filter(pk=existing.pk).update(
            occurrences=F('occurrences') + 1,
            last_seen_at=timezone.now(),
            details=details or existing.details,
        )
        return existing


# ==============================================================================
# CAPTURE DES RÉVISIONS ET DROITS D'ACCÈS
# ==============================================================================

def capture_course_revisions(order, source, captured_by=None):
    """
    Pour chaque ligne de formation : verrouille la formation (id croissant), lit
    Course.published_revision APRÈS le verrou et enregistre la révision exacte achetée,
    puis crée le droit d'accès correspondant. Idempotent (OneToOne sur la ligne).
    Doit être appelée dans la transaction qui détient le verrou de la commande.
    """
    from apps.courses.access import grant_purchase_access
    from apps.courses.models import AccessGrant, Course

    course_items = [item for item in order.items.order_by('id') if item.course_id]
    if not course_items:
        return []

    locked_courses = {}
    for course_id in sorted({item.course_id for item in course_items}):
        locked_courses[course_id] = Course.objects.select_for_update().get(pk=course_id)

    links = []
    for item in course_items:
        link = PaymentRevisionLink.objects.filter(order_item=item).select_related('course_revision').first()
        course = locked_courses[item.course_id]
        if link is None:
            if course.published_revision_id is None:
                # Décision R3 : aucun accès sans version pédagogique identifiable.
                record_reconciliation(
                    order.pk, PaymentReconciliation.Kind.NO_PUBLISHED_REVISION, order_item_id=item.pk,
                    details={'course_id': course.pk},
                )
                logger.error("Commande #%s ligne #%s : formation #%s sans révision publiée, accès non attribué.",
                             order.pk, item.pk, course.pk)
                continue
            link = PaymentRevisionLink.objects.create(
                order=order,
                order_item=item,
                course=course,
                course_revision_id=course.published_revision_id,
                source=source,
                captured_by=captured_by,
            )
        links.append(link)

        if order.user_id is None:
            record_reconciliation(
                order.pk, PaymentReconciliation.Kind.CONFIRMATION_FAILED, order_item_id=item.pk,
                details={'reason': 'commande sans utilisateur : droit d\'accès non attribuable'},
            )
            continue

        already_active = AccessGrant.objects.filter(
            user_id=order.user_id, course_id=course.pk, status=AccessGrant.Status.ACTIVE,
        ).exclude(order_item=item).exists()
        grant, created = grant_purchase_access(item, link.course_revision, granted_by=captured_by)
        if created and already_active:
            record_reconciliation(
                order.pk, PaymentReconciliation.Kind.DUPLICATE_PURCHASE, order_item_id=item.pk,
                details={'course_id': course.pk, 'grant_id': grant.pk},
            )
    return links


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


def process_order_stock_and_fulfillment(order, source=PaymentRevisionLink.Source.ADMIN_FULFILLMENT, captured_by=None):
    """
    Traitement commercial d'une commande payée, dans la transaction de l'appelant qui
    détient déjà le verrou de la commande :
      1. capture des révisions et droits d'accès (verrous Course, id croissant) ;
      2. déduction de stock et mouvements SALE (verrous Product, id croissant) ;
      3. événement Outbox de génération du reçu PDF (traité après commit).
    Toute erreur remonte et annule l'ensemble : aucun échec n'est absorbé silencieusement.
    """
    if order.stock_updated:
        logger.info("Stock déjà mis à jour pour la commande #%s. Opération ignorée.", order.id)
        return False

    order_user = order.user

    # 1. Formations : capture de la révision publiée et attribution des droits.
    capture_course_revisions(order, source=source, captured_by=captured_by)

    # 2. Produits physiques : regroupement par product_id puis verrouillage déterministe.
    physical_items = [item for item in order.items.select_related('product').all() if item.product_id]
    qty_by_product_id = {}
    for item in physical_items:
        qty_by_product_id[item.product_id] = qty_by_product_id.get(item.product_id, 0) + item.quantity

    from apps.products.models import Product
    locked_products = {}
    for pid in sorted(qty_by_product_id.keys()):
        product = Product.objects.select_for_update().get(pk=pid)
        total_required = qty_by_product_id[pid]
        if product.stock is not None and product.stock < total_required:
            raise InsufficientStockError(
                f"Stock insuffisant pour '{product.name}' (commande #{order.id}). "
                f"Stock actuel: {product.stock}, requis: {total_required}"
            )
        locked_products[pid] = product

    for item in physical_items:
        product = locked_products[item.product_id]
        Product.objects.filter(pk=product.pk).update(stock=F('stock') - item.quantity)
        _record_stock_movement_strict(
            product=product,
            quantity=-item.quantity,
            movement_type=StockMovement.MovementType.SALE,
            order=order,
            user=order_user,
            comment=f"Vente - commande #{order.id}",
        )

    order.stock_updated = True

    # 3. Reçu PDF : hors transaction (I/O réseau), via l'Outbox.
    if not order.receipt:
        from .outbox import enqueue
        enqueue(order, OutboxEvent.EventType.PDF_RECEIPT, f"pdf-receipt:order:{order.pk}")

    return True


# ==============================================================================
# CONFIRMATION DU PAIEMENT
# ==============================================================================

def _validate_currency(order, currency):
    if currency is None:
        return
    clean_currency = str(currency).strip().upper()
    if clean_currency not in SUPPORTED_CURRENCIES:
        logger.error("confirm_order_payment: Devise non supportée pour #%s: %s", order.id, currency)
        raise InvalidPaymentAmountError(f"Devise non supportée: {currency}")


def _validate_amount(order, amount_received):
    if amount_received is None:
        return
    try:
        received_decimal = Decimal(str(amount_received).strip())
    except (InvalidOperation, ValueError, TypeError):
        logger.error("confirm_order_payment: Format de montant invalide pour #%s.", order.id)
        raise InvalidPaymentAmountError(f"Format de montant invalide: {amount_received}")
    if received_decimal != order.total:
        logger.error(
            "confirm_order_payment: Montant incohérent pour commande #%s. Reçu: %s, Attendu: %s",
            order.id, received_decimal, order.total
        )
        raise InvalidPaymentAmountError(f"Montant incohérent ({received_decimal} ≠ {order.total})")


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
    Point d'entrée unique de la confirmation interne d'un paiement (transaction unique) :
    verrou de la commande, contrôles (référence, état, devise, montant EXACT), date de
    paiement (une seule fois), capture des révisions, droits d'accès, stock, et
    événements Outbox (reçu, email). Si une étape échoue, rien n'est conservé.

    ``amount_received`` / ``currency`` : obligatoires pour les appels issus du prestataire
    (vérifiés par les vues) ; None n'est accepté que pour les appels internes de confiance.

    Retourne : (bool, Order, str) — str ∈ {'confirmed', 'already_paid', 'order_not_found', 'invalid_status'}.
    """
    try:
        order = Order.objects.select_for_update().get(id=order_id)
    except Order.DoesNotExist:
        logger.error("confirm_order_payment: Commande #%s introuvable.", order_id)
        return False, None, "order_not_found"

    clean_ref = str(transaction_ref).strip()[:100] if transaction_ref else None

    # 1. Unicité inter-commandes de la référence prestataire
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

    # 2. Une référence existante ne doit jamais être remplacée ou contredite silencieusement
    if clean_ref and order.paygate_tx_id and order.paygate_tx_id != clean_ref:
        logger.error(
            "confirm_order_payment: Incohérence de référence pour commande #%s : existante='%s', reçue='%s'",
            order.id, order.paygate_tx_id, clean_ref
        )
        raise PaymentProcessingError(
            f"Incohérence de référence pour commande #{order.id} : référence existante "
            f"'{order.paygate_tx_id}' différente de '{clean_ref}'."
        )

    # 3. Idempotence : notification répétée sans effet (paid_at conservé)
    if order.payment_status or order.status == 'paid':
        logger.info("confirm_order_payment: Commande #%s déjà marquée payée. Aucun nouveau traitement.", order.id)
        return False, order, "already_paid"

    # 4. États irréversibles
    if order.status in ('cancelled', 'refunded'):
        logger.warning(
            "confirm_order_payment: Commande #%s rejetée car son statut actuel est '%s'.",
            order.id, order.status
        )
        return False, order, "invalid_status"

    # 5. Devise et montant exacts
    _validate_currency(order, currency)
    _validate_amount(order, amount_received)

    # 6. Traitement commercial (révisions, droits, stock, reçu)
    process_order_stock_and_fulfillment(order, source=PaymentRevisionLink.Source.PAYMENT_CONFIRMATION)

    # 7. Statuts financiers
    order.status = 'paid'
    order.payment_status = True
    update_fields = ['status', 'payment_status', 'stock_updated', 'updated_at']
    if order.paid_at is None:
        order.paid_at = timezone.now()
        update_fields.append('paid_at')
    if clean_ref and not order.paygate_tx_id:
        order.paygate_tx_id = clean_ref
        update_fields.append('paygate_tx_id')
    if payment_method and not order.payment_method:
        order.payment_method = str(payment_method)[:50]
        update_fields.append('payment_method')
    order.save(update_fields=update_fields)

    # 8. Notification client : événement Outbox (traité après commit)
    if send_email:
        from .outbox import enqueue
        enqueue(order, OutboxEvent.EventType.PAYMENT_EMAIL, f"payment-email:order:{order.pk}")

    logger.info("confirm_order_payment: Commande #%s confirmée avec succès.", order.id)
    return True, order, "confirmed"


def confirm_provider_payment(order_id, *, provider_reference, amount, currency, channel):
    """
    Confirmation déclenchée par le prestataire (webhook ou interrogation API) après
    vérification de l'état « Paid ». Tout échec est consigné en réconciliation dans une
    transaction distincte : CashPay a potentiellement encaissé, le rollback SQL n'y change rien.
    Retourne (succès: bool, raison: str).
    """
    base_details = {'channel': channel, 'amount': str(amount), 'currency': currency}
    try:
        confirmed, order, reason = confirm_order_payment(
            order_id=order_id,
            transaction_ref=provider_reference,
            amount_received=amount,
            currency=currency,
        )
    except InvalidPaymentAmountError as err:
        record_reconciliation(order_id, PaymentReconciliation.Kind.AMOUNT_MISMATCH,
                              provider_reference=provider_reference or '', details=dict(base_details, error=str(err)))
        return False, 'amount_mismatch'
    except Exception as err:
        record_reconciliation(order_id, PaymentReconciliation.Kind.CONFIRMATION_FAILED,
                              provider_reference=provider_reference or '',
                              details=dict(base_details, error=f"{type(err).__name__}: {err}"))
        raise

    if reason == 'invalid_status':
        record_reconciliation(order_id, PaymentReconciliation.Kind.PAID_ON_CLOSED_ORDER,
                              provider_reference=provider_reference or '',
                              details=dict(base_details, order_status=order.status))
        return False, reason
    if reason == 'order_not_found':
        return False, reason
    return True, reason
