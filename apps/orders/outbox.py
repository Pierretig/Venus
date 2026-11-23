"""
Outbox transactionnel et worker.

Principes :
- Les événements sont créés DANS la transaction métier (confirmation de paiement) :
  si elle échoue, aucun événement n'est conservé.
- Unicité de l'événement : contrainte ``uniq_outbox_idempotency_key``.
- Unicité de l'effet métier : portée par le handler (ex. reçu déjà présent) et, pour les
  droits d'accès, par les contraintes SQL d'AccessGrant/PaymentRevisionLink (créés de
  façon synchrone dans la transaction de paiement, pas par le worker).
- Concurrence entre workers : réclamation par ``SELECT … FOR UPDATE SKIP LOCKED`` dans une
  transaction courte, puis lease durable (``locked_until`` + ``lease_token``). Le verrou SQL
  est relâché avant le traitement ; seul le détenteur du jeton peut clore l'événement.
- Lease expirée : l'événement redevient réclamable (aucune réinitialisation de masse).
- Dispatch immédiat après commit (``transaction.on_commit``) pour conserver le comportement
  historique (email et reçu envoyés juste après le paiement) ; le worker
  ``manage.py process_outbox`` reprend tout ce qui a échoué ou n'a pas été dispatché.
"""
import logging
import uuid
from datetime import timedelta

from django.conf import settings
from django.core.files.base import ContentFile
from django.db import transaction
from django.db.models import F, Q
from django.utils import timezone

from .models import Order, OutboxEvent

logger = logging.getLogger(__name__)

# 5 minutes : largement au-dessus du traitement le plus long (génération PDF + envoi
# Cloudinary + SMTP, timeouts réseau compris) et assez court pour qu'un worker tué soit
# relayé rapidement.
LEASE_SECONDS = getattr(settings, 'OUTBOX_LEASE_SECONDS', 300)
# 8 tentatives avec backoff exponentiel plafonné (30 s … 1 h) couvrent ~4 h d'indisponibilité
# SMTP / stockage avant passage en FAILED (reprise manuelle possible via l'admin).
MAX_ATTEMPTS = getattr(settings, 'OUTBOX_MAX_ATTEMPTS', 8)
BACKOFF_BASE_SECONDS = 30
BACKOFF_MAX_SECONDS = 3600


class PermanentOutboxError(Exception):
    """Erreur définitive : inutile de réessayer (passe directement en FAILED)."""


# ---------------------------------------------------------------------------
# Production d'événements (dans la transaction métier)
# ---------------------------------------------------------------------------

def enqueue(order, event_type, idempotency_key, payload=None, course=None):
    """Crée l'événement s'il n'existe pas (idempotent sur idempotency_key)."""
    event, created = OutboxEvent.objects.get_or_create(
        idempotency_key=idempotency_key,
        defaults={
            'order': order,
            'event_type': event_type,
            'payload': payload or {},
            'course': course,
        },
    )
    if created:
        _schedule_eager_dispatch(event.pk)
    return event, created


def _schedule_eager_dispatch(event_id):
    if getattr(settings, 'OUTBOX_EAGER_DISPATCH', True):
        transaction.on_commit(lambda: dispatch_events([event_id]))


# ---------------------------------------------------------------------------
# Réclamation et traitement
# ---------------------------------------------------------------------------

def _claimable_filter(now):
    return (
        Q(status=OutboxEvent.Status.PENDING, available_at__lte=now)
        | Q(status=OutboxEvent.Status.PROCESSING, locked_until__lt=now)
    )


def claim_events(limit=20, event_ids=None):
    """
    Réclame jusqu'à ``limit`` événements disponibles (ou lease expirée) et pose une lease.
    Transaction courte : le verrou de ligne est relâché au commit, avant tout traitement.
    """
    now = timezone.now()
    token = uuid.uuid4()
    with transaction.atomic():
        qs = OutboxEvent.objects.filter(_claimable_filter(now))
        if event_ids is not None:
            qs = qs.filter(pk__in=event_ids)
        ids = list(
            qs.select_for_update(skip_locked=True).order_by('available_at', 'id').values_list('pk', flat=True)[:limit]
        )
        if not ids:
            return [], token
        OutboxEvent.objects.filter(pk__in=ids).update(
            status=OutboxEvent.Status.PROCESSING,
            processing_at=now,
            locked_until=now + timedelta(seconds=LEASE_SECONDS),
            lease_token=token,
            attempts=F('attempts') + 1,
        )
    return list(OutboxEvent.objects.filter(pk__in=ids, lease_token=token).order_by('id')), token


def _backoff(attempts):
    return min(BACKOFF_MAX_SECONDS, BACKOFF_BASE_SECONDS * (2 ** max(0, attempts - 1)))


def _finish(event, token, error=None, permanent=False):
    """Clôt l'événement uniquement si la lease est toujours détenue par ce worker."""
    now = timezone.now()
    owned = OutboxEvent.objects.filter(pk=event.pk, lease_token=token, status=OutboxEvent.Status.PROCESSING)
    if error is None:
        updated = owned.update(status=OutboxEvent.Status.SUCCESS, processed_at=now, locked_until=None,
                               lease_token=None, last_error='')
    elif permanent or event.attempts >= MAX_ATTEMPTS:
        updated = owned.update(status=OutboxEvent.Status.FAILED, locked_until=None, lease_token=None,
                               last_error=error[:4000])
    else:
        updated = owned.update(status=OutboxEvent.Status.PENDING, locked_until=None, lease_token=None,
                               available_at=now + timedelta(seconds=_backoff(event.attempts)),
                               last_error=error[:4000])
    if not updated:
        logger.warning("Outbox #%s : lease perdue avant la fin du traitement (effet idempotent rejoué ailleurs).", event.pk)
    return bool(updated)


def process_event(event, token):
    handler = HANDLERS.get(event.event_type)
    if handler is None:
        return _finish(event, token, error=f"Aucun handler pour {event.event_type}", permanent=True)
    try:
        handler(event)
    except PermanentOutboxError as exc:
        logger.error("Outbox #%s (%s) échec définitif : %s", event.pk, event.event_type, exc)
        return _finish(event, token, error=f"{type(exc).__name__}: {exc}", permanent=True)
    except Exception as exc:  # erreur temporaire : réessai avec backoff, erreur enregistrée
        logger.warning("Outbox #%s (%s) échec (tentative %s) : %s", event.pk, event.event_type, event.attempts, exc)
        return _finish(event, token, error=f"{type(exc).__name__}: {exc}")
    return _finish(event, token)


def process_batch(limit=20):
    events, token = claim_events(limit=limit)
    for event in events:
        process_event(event, token)
    return len(events)


def dispatch_events(event_ids):
    """Traitement immédiat (post-commit) d'événements précis ; le worker prend le relais en cas d'échec."""
    try:
        events, token = claim_events(limit=len(event_ids), event_ids=event_ids)
    except Exception as exc:
        logger.error("Dispatch immédiat outbox impossible (%s) : reprise par le worker.", exc)
        return 0
    for event in events:
        process_event(event, token)
    return len(events)


# ---------------------------------------------------------------------------
# Handlers (effets idempotents)
# ---------------------------------------------------------------------------

def handle_pdf_receipt(event):
    from .utils import generate_order_pdf
    order = Order.objects.get(pk=event.order_id)
    if order.receipt:
        return
    pdf_content = generate_order_pdf(order)
    if not pdf_content:
        raise PermanentOutboxError("Générateur PDF indisponible ou contenu vide.")
    filename = f"recu_venus_luna_{order.id}.pdf"
    order.receipt.save(filename, ContentFile(pdf_content), save=False)
    # update() ciblé : ne déclenche pas les signaux post_save de la commande.
    Order.objects.filter(Q(receipt='') | Q(receipt__isnull=True), pk=order.pk).update(receipt=order.receipt.name)


def handle_payment_email(event):
    from .utils import send_order_paid_email
    order = Order.objects.get(pk=event.order_id)
    if not (order.email or (order.user and order.user.email)):
        raise PermanentOutboxError("Aucune adresse email pour cette commande.")
    sent = send_order_paid_email(order)
    if sent is False:
        raise RuntimeError("Envoi de l'email de confirmation refusé par le backend.")


HANDLERS = {
    OutboxEvent.EventType.PDF_RECEIPT: handle_pdf_receipt,
    OutboxEvent.EventType.PAYMENT_EMAIL: handle_payment_email,
}
