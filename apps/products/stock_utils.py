"""
Utilitaires de gestion de stock et de réservation temporaire.

Ces helpers centralisent la logique de réservation 15 min pour éviter
la duplication (DRY) et garantir un comportement atomique et sûr même
avec plusieurs clients connectés simultanément.
"""
from decimal import Decimal
from django.utils import timezone
from django.db import transaction
from django.db.models import Sum

from .models import Product, StockReservation

# Durée de réservation par défaut (en minutes)
RESERVATION_MINUTES = 15


def get_available_stock(product, exclude_session_key=None):
    """
    Retourne le stock réellement vendable d'un produit, en déduisant
    les réservations actives (non expirées) d'autres sessions.
    """
    now = timezone.now()
    qs = product.reservations.filter(expires_at__gt=now)
    if exclude_session_key:
        qs = qs.exclude(session_key=exclude_session_key)
    reserved_qty = qs.aggregate(Sum('quantity'))['quantity__sum'] or 0
    return max(0, product.stock - reserved_qty)


def _ensure_session_key(request_or_key):
    """Extrait la session_key d'une requête ou utilise directement la clé."""
    if hasattr(request_or_key, 'session') and hasattr(request_or_key.session, 'session_key'):
        return request_or_key.session.session_key
    return str(request_or_key or '')


def reserve_stock(product, session_key, quantity=1):
    """
    Réserve `quantity` unités d'un produit pour une session pendant
    RESERVATION_MINUTES minutes. La vérification de disponibilité et
    la création de la réservation sont atomiques (blocage de ligne).

    Retourne True si la réservation a réussi, sinon False.
    """
    quantity = max(1, int(quantity))
    session_key = _ensure_session_key(session_key)
    if not session_key:
        return False

    with transaction.atomic():
        # Verrouille la ligne produit pour éviter les courses critiques
        product = Product.objects.select_for_update().get(pk=product.pk)

        # Libère d'abord les réservations antérieures de cette session pour ce produit
        # (on ne cumule pas, on remplace) — évite les réservations fantômes.
        product.reservations.filter(session_key=session_key).delete()

        available = get_available_stock(product, exclude_session_key=session_key)
        if available < quantity:
            return False

        expires_at = timezone.now() + timezone.timedelta(minutes=RESERVATION_MINUTES)
        StockReservation.objects.create(
            product=product,
            session_key=session_key,
            quantity=quantity,
            expires_at=expires_at,
        )
        return True


def release_reservation_session(session_key):
    """
    Libère toutes les réservations d'une session (panier vidé, paiement
    réussi, abandon). Retourne le nombre de réservations supprimées.
    """
    session_key = _ensure_session_key(session_key)
    if not session_key:
        return 0
    deleted, _ = StockReservation.objects.filter(session_key=session_key).delete()
    return deleted


def release_expired_reservations():
    """
    Supprime toutes les réservations expirées. À appeler périodiquement
    (cron) pour libérer le stock des clients qui n'ont pas payé.
    Retourne le nombre de réservations libérées.
    """
    now = timezone.now()
    deleted, _ = StockReservation.objects.filter(expires_at__lte=now).delete()
    return deleted


def sync_reservations_from_cart(session_key, cart_items):
    """
    Synchronise les réservations d'une session avec le contenu du panier.
    `cart_items` est une liste de dicts {'product': product, 'quantity': int}.
    Crée/met à jour les réservations et supprime celles des produits
    retirés du panier. Retourne un booléen indiquant si le panier est
    entièrement réservable (aucun produit en rupture).
    """
    session_key = _ensure_session_key(session_key)
    if not session_key:
        return False

    current_product_ids = set()

    with transaction.atomic():
        for item in cart_items:
            product = item['product']
            qty = max(1, int(item['quantity']))
            current_product_ids.add(product.pk)
            ok = reserve_stock(product, session_key, qty)
            if not ok:
                return False

        # Supprime les réservations des produits ne figurant plus au panier
        StockReservation.objects.filter(session_key=session_key).exclude(
            product_id__in=current_product_ids
        ).delete()

    return True


def is_cart_available(cart_items, session_key=None):
    """
    Vérifie si tous les articles du panier sont disponibles en quantité
    suffisante (tenant compte des réservations des autres sessions).
    `cart_items` : liste de dicts {'product': Product, 'quantity': int}.
    """
    for item in cart_items:
        product = item['product']
        requested = max(1, int(item['quantity']))
        available = get_available_stock(product, exclude_session_key=session_key)
        if available < requested:
            return False
    return True


def cart_total_reserved(cart_items):
    """Calcule le nombre total d'unités réservées dans le panier."""
    total = 0
    for item in cart_items:
        total += max(1, int(item['quantity']))
    return total
