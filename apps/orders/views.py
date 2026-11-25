import json
import logging
import hmac
import hashlib
from decimal import Decimal, InvalidOperation
from urllib.parse import urlencode

from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.http import HttpResponse, JsonResponse, Http404
from django.views.decorators.csrf import csrf_exempt
from django.conf import settings

# Bibliothèques PDF
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors

from .forms import CheckoutForm
from .models import Order, OrderItem, ShippingAddress, ShippingZone
from .utils import send_order_pending_payment_email, send_order_paid_email
from apps.products.models import Product, StockReservation
from apps.core.ratelimit import ratelimit
from apps.products.stock_utils import (
    get_available_stock, reserve_stock, release_reservation_session,
    sync_reservations_from_cart, is_cart_available,
)
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

logger = logging.getLogger(__name__)

# CONFIGURATION (CashPay remplace BKAPAY)
BKAPAY_PUBLIC_KEY = getattr(settings, 'BKAPAY_PUBLIC_KEY', None)
BKAPAY_SECRET_WEBHOOK = getattr(settings, 'BKAPAY_SECRET_WEBHOOK', None)

# CashPay config
CASHPAY_SECRET_WEBHOOK = getattr(settings, 'CASHPAY_SECRET_WEBHOOK', None)


def _can_access_order(request, order):
    """
    Vérifie si l'utilisateur courant a le droit d'accéder à la commande :
    - Administrateurs (is_staff) : toujours autorisé.
    - Commande liée à un compte : uniquement si l'utilisateur est connecté et propriétaire.
    - Token signé valide dans l'URL (retour CashPay cross-origin) : autorisé.
    - Commande passée en invité (order.user is None) : autorisé si l'ID correspond à la session active du client.
    """
    if request.user.is_authenticated and request.user.is_staff:
        return True
    if order.user_id is not None and request.user.is_authenticated and request.user.id == order.user_id:
        return True
    # Vérification par token signé (utilisé dans redirect_url pour garantir le retour même si la session est perdue)
    token = request.GET.get('token')
    if token:
        try:
            from django.core import signing
            signed_id = signing.loads(token, salt='cashpay-return', max_age=86400)
            if signed_id == order.id:
                request.session['last_order_id'] = order.id
                return True
        except Exception:
            pass
    # Commande invité : vérification de la session
    return request.session.get('last_order_id') == order.id


@user_passes_test(lambda u: u.is_authenticated and u.is_staff)
def dashboard_view(request):
    # On récupère les vraies données de ta base
    orders = Order.objects.all()
    total_orders = orders.count()
    total_revenue = orders.filter(payment_status=True).aggregate(Sum('total'))['total__sum'] or 0
    pending_orders = orders.filter(status='pending').count()
    total_customers = orders.values('email').distinct().count()

    context = {
        'total_orders': total_orders,
        'total_revenue': total_revenue,
        'total_customers': total_customers,
        'pending_orders': pending_orders,
        'recent_orders': orders.order_by('-created_at')[:10],
        'today': timezone.now(),
        # Valeurs vides pour éviter les erreurs JS des graphiques
        'chart_labels': ["Lundi", "Mardi", "Mercredi"],
        'chart_values': [0, 0, total_revenue],
        'pie_labels': ["Ventes"],
        'pie_values': [100],
    }
    return render(request, 'admin_custom/dashboard.html', context)


# =====================================================
# PANIER (LOGIQUE UTILITAIRE)
# =====================================================

def get_cart_data(request):
    cart = request.session.get("cart", {})
    items = []
    total = Decimal("0")
    for p_id, data in cart.items():
        try:
            product = Product.objects.get(pk=p_id)
            qty = int(data["quantity"])
            subtotal = product.price * qty
            total += subtotal
            items.append({"product": product, "quantity": qty, "subtotal": subtotal})
        except Product.DoesNotExist:
            continue
    return items, total


def cart_detail(request):
    items, total = get_cart_data(request)
    return render(request, 'orders/cart.html', {'cart_items': items, 'cart_total': total})


def cart_add(request, product_id):
    cart = request.session.get('cart', {})
    product = get_object_or_404(Product, id=product_id)
    p_id = str(product_id)
    try:
        quantity = int(request.POST.get('quantity', 1))
    except (TypeError, ValueError):
        quantity = 1
    quantity = max(1, quantity)

    # Empêche l'ajout d'un produit indisponible (en rupture de stock)
    if product.stock is None or product.stock <= 0:
        messages.error(request, f"« {product.name} » est actuellement en rupture de stock.")
        return redirect(request.META.get('HTTP_REFERER', 'orders:cart_detail'))

    current_in_cart = 0
    if p_id in cart and isinstance(cart[p_id], dict):
        current_in_cart = int(cart[p_id].get('quantity', 0))
    new_qty = current_in_cart + quantity

    # Vérifie la disponibilité en tenant compte des réservations des autres sessions
    available = get_available_stock(product, exclude_session_key=request.session.session_key)
    if available < new_qty:
        messages.error(request, f"Stock insuffisant pour « {product.name} » (disponible : {available}).")
        return redirect(request.META.get('HTTP_REFERER', 'orders:cart_detail'))

    if p_id not in cart:
        cart[p_id] = {'quantity': 0, 'price': str(product.price)}
    cart[p_id]['quantity'] = new_qty
    request.session['cart'] = cart

    # Réserve la quantité pendant 15 minutes (atomique)
    if request.session.session_key:
        reserve_stock(product, request.session.session_key, new_qty)

    messages.success(request, f"{product.name} ajouté au panier.")
    return redirect(request.META.get('HTTP_REFERER', 'orders:cart_detail'))


def cart_count_api(request):
    cart = request.session.get("cart", {})
    total_qty = 0
    for item in cart.values():
        try:
            total_qty += int(item.get("quantity", 0))
        except (TypeError, ValueError, AttributeError):
            continue
    return JsonResponse({"count": total_qty})


def cart_update(request, product_id):
    cart = request.session.get('cart', {})
    p_id = str(product_id)
    if p_id in cart:
        try:
            qty = int(request.POST.get('quantity', 1))
            if qty > 0:
                product = Product.objects.filter(id=product_id).first()
                if product and request.session.session_key:
                    # Vérifie la disponibilité avant de mettre à jour
                    available = get_available_stock(product, exclude_session_key=request.session.session_key)
                    if available < qty:
                        messages.error(request, f"Stock insuffisant pour « {product.name} » (disponible : {available}).")
                        return redirect('orders:cart_detail')
                cart[p_id]['quantity'] = qty
                # Met à jour la réservation
                if request.session.session_key:
                    reserve_stock(product, request.session.session_key, qty)
            else:
                del cart[p_id]
                # Libère la réservation de ce produit pour cette session
                if request.session.session_key:
                    StockReservation.objects.filter(
                        product_id=product_id, session_key=request.session.session_key
                    ).delete()
        except (ValueError, TypeError):
            pass
    request.session['cart'] = cart
    return redirect('orders:cart_detail')


def cart_remove(request, product_id):
    cart = request.session.get('cart', {})
    if str(product_id) in cart:
        del cart[str(product_id)]
        request.session['cart'] = cart
        # Libère la réservation de ce produit pour cette session
        if request.session.session_key:
            StockReservation.objects.filter(
                product_id=product_id, session_key=request.session.session_key
            ).delete()
    return redirect('orders:cart_detail')


# =====================================================
# PROCESSUS DE COMMANDE (CHECKOUT & CASHPAY)
# =====================================================

def _get_checkout_initial(user):
    """
    Préremplit les champs de commande pour un client connecté :
      - full_name : prénom + nom depuis User (repli sur username si vide)
      - email     : adresse e-mail du compte
      - phone     : téléphone depuis Profile.phone (si existant)
      - address   : adresse depuis Profile.address (si existant)
      - city      : ville depuis Profile.city (repli sur 'Lomé' si vide)
      - country   : 'Togo'
    Pour un invité (non connecté) ou sans profil, retourne les valeurs par défaut
    sans lever d'exception.
    """
    if not user.is_authenticated:
        return {}

    full_name = f"{user.first_name} {user.last_name}".strip() or user.username or ''

    initial = {
        'full_name': full_name,
        'email': user.email or '',
        'city': 'Lomé',
        'country': 'Togo',
    }

    if hasattr(user, 'profile'):
        profile = user.profile
        if profile.phone:
            initial['phone'] = profile.phone
        if profile.address:
            initial['address'] = profile.address
        if profile.city:
            initial['city'] = profile.city

    return initial


class _CashPayNotConfiguredError(RuntimeError):
    """Levée lorsque CashPay n'est pas configuré (aucune requête réseau émise)."""
    pass


def _initialize_cashpay_for_order(request, order, description=None):
    """
    Initialise le lien de paiement CashPay pour une commande en attente.
    Ne doit jamais être appelée à l'intérieur d'une transaction DB ouverte,
    ni écraser une référence existante ou modifier une commande déjà payée.
    """
    if order.payment_status or order.status != 'pending':
        return order.payment_url or ''

    if order.paygate_tx_id:
        return order.payment_url or ''

    callback_url = getattr(settings, 'CASHPAY_WEBHOOK_URL', None) or request.build_absolute_uri(
        reverse('orders:cashpay_webhook')
    )

    # Token signé pour authentifier le retour CashPay de manière infaillible
    from django.core import signing
    token = signing.dumps(order.id, salt='cashpay-return')
    redirect_url = request.build_absolute_uri(
        reverse('orders:cashpay_return', kwargs={'order_id': order.id})
    ) + f"?token={token}"

    from .cashpay_service import CashPayService
    from .payment_processing import record_reconciliation
    from .models import PaymentReconciliation

    cashpay = CashPayService()
    if not cashpay.is_configured():
        raise _CashPayNotConfiguredError("CashPay n'est pas configuré (CASHPAY_* manquantes).")

    # S'assurer que le numéro de téléphone commence par '+'
    raw_phone = (order.shipping_address.phone if hasattr(order, 'shipping_address') else '') or ''
    phone_formatted = raw_phone.strip()
    if phone_formatted and not phone_formatted.startswith('+'):
        phone_formatted = f"+{phone_formatted}"

    try:
        resp = cashpay.create_link2pay_order(
            amount=order.total,
            currency='XOF',
            merchant_reference=str(order.id),
            description=description or f"Commande #{order.id} Venus Luna",
            callback_url=callback_url,
            phone=phone_formatted or "+22890000000",
            type_notif=["SMS", "MAIL"],
            redirect_url=redirect_url,
        )
    except Exception as exc:
        # Un timeout ou une erreur réseau ne prouve pas que CashPay n'a pas créé la transaction.
        record_reconciliation(
            order.id,
            PaymentReconciliation.Kind.PROVIDER_STATE,
            provider_reference=order.paygate_tx_id or '',
            details={'channel': 'cashpay_init', 'uncertain': True, 'error': str(exc)},
        )
        raise

    # bill_url : URL de la facture CashPay
    # order_reference : référence interne CashPay (pour le polling API fallback)
    payment_url = resp.get('bill_url') or resp.get('payment_url')
    cashpay_order_ref = resp.get('order_reference', '') or None

    if not payment_url:
        if cashpay_order_ref:
            Order.objects.filter(
                id=order.id, payment_status=False, status='pending', paygate_tx_id__isnull=True
            ).update(paygate_tx_id=cashpay_order_ref)
        record_reconciliation(
            order.id,
            PaymentReconciliation.Kind.PROVIDER_STATE,
            provider_reference=cashpay_order_ref or '',
            details={'channel': 'cashpay_init', 'uncertain': True, 'error': 'bill_url manquant'},
        )
        raise RuntimeError("CashPay n'a pas retourné de bill_url dans la réponse.")

    if cashpay_order_ref:
        Order.objects.filter(
            id=order.id, payment_status=False, status='pending', paygate_tx_id__isnull=True
        ).update(payment_url=payment_url, paygate_tx_id=cashpay_order_ref)
    Order.objects.filter(
        id=order.id, payment_status=False, status='pending', payment_url__isnull=True
    ).update(payment_url=payment_url)

    send_order_pending_payment_email(order, payment_url)

    # Mémoriser en session pour la page relay
    request.session['cashpay_bill_url'] = payment_url
    request.session['cashpay_order_ref'] = cashpay_order_ref or ''
    return payment_url


@ratelimit(rate='10/m', key='ip', block=True, redirect_url='orders:cart_detail', error_message="Trop de tentatives de commande. Veuillez patienter une minute.")
def checkout(request):
    items, total = get_cart_data(request)
    zones = ShippingZone.objects.all()

    if not items:
        messages.warning(request, "Panier vide.")
        return redirect('orders:cart_detail')

    # Vérifie la disponibilité de tous les articles avant le paiement.
    # Empêche le paiement si un produit est devenu indisponible.
    if not is_cart_available(items, session_key=request.session.session_key):
        messages.error(
            request,
            "Certains produits de votre panier ne sont plus disponibles en quantité suffisante. Veuillez ajuster votre panier.",
        )
        return redirect('orders:cart_detail')

    if request.method == 'POST':
        form = CheckoutForm(request.POST)
        if form.is_valid():
            zone_id = request.POST.get('shipping_zone')
            shipping_price = Decimal("0")
            if zone_id:
                try:
                    zone = ShippingZone.objects.get(pk=zone_id)
                    shipping_price = zone.price
                except (ShippingZone.DoesNotExist, ValueError):
                    shipping_price = Decimal("0")

            expected_total = total + shipping_price
            if expected_total < 200:
                messages.error(request, f"Le montant ({expected_total} F) est trop bas.")
                return redirect('orders:cart_detail')

            order = None
            try:
                # Écritures locales atomiques uniquement (aucun appel réseau dans la transaction)
                with transaction.atomic():
                    if request.session.session_key:
                        if not sync_reservations_from_cart(request.session.session_key, items):
                            raise ValueError("stock_unavailable")

                    order = Order.objects.create(
                        user=request.user if request.user.is_authenticated else None,
                        email=form.cleaned_data['email'],
                        shipping_price=shipping_price,
                        status='pending',
                        payment_status=False
                    )

                    for item in items:
                        OrderItem.objects.create(
                            order=order,
                            product=item['product'],
                            name=item['product'].name,
                            price=item['product'].price,
                            quantity=item['quantity']
                        )

                    order.recalc_total()
                    if order.total < 200:
                        raise ValueError("amount_too_low")

                    ShippingAddress.objects.create(
                        order=order,
                        full_name=form.cleaned_data['full_name'],
                        address=form.cleaned_data['address'],
                        phone=form.cleaned_data.get('phone', ''),
                        city=form.cleaned_data.get('city', 'Lomé'),
                        country=form.cleaned_data.get('country', 'Togo')
                    )
            except ValueError as val_err:
                if str(val_err) == "stock_unavailable":
                    messages.error(
                        request,
                        "Certains produits de votre panier ne sont plus disponibles en quantité suffisante. Veuillez ajuster votre panier.",
                    )
                else:
                    messages.error(request, f"Le montant ({expected_total} F) est trop bas.")
                return redirect('orders:cart_detail')
            except Exception as e:
                logger.error(f"Erreur création locale commande checkout : {e}", exc_info=True)
                messages.error(
                    request,
                    "Un problème est survenu lors de l'enregistrement de votre commande. "
                    "Veuillez réessayer dans quelques instants."
                )
                return render(request, 'orders/checkout.html', {
                    'form': form, 'cart_items': items, 'total': total, 'zones': zones
                })

            # Mémoriser l'ID de la commande en session pour permettre l'accès légitime aux invités
            request.session['last_order_id'] = order.id

            # --- Appel réseau CashPay HORS transaction DB ---
            # En cas d'échec réseau / timeout / réponse invalide, la commande reste
            # conservée en base (pending) et l'utilisateur peut réessayer sans doublon.
            try:
                _initialize_cashpay_for_order(request, order)
            except Exception as e:
                logger.error(f"Erreur initialisation CashPay commande #{order.id} : {e}", exc_info=True)
                messages.warning(
                    request,
                    "Votre commande a bien été enregistrée, mais la connexion à CashPay a échoué temporairement. "
                    "Vous pouvez réessayer de générer le lien de paiement ci-dessous."
                )

            return redirect(reverse('orders:cashpay_payment_page', kwargs={'order_id': order.id}))
    else:
        initial = _get_checkout_initial(request.user)
        form = CheckoutForm(initial=initial) if initial else CheckoutForm()

    return render(request, 'orders/checkout.html', {
        'form': form, 'cart_items': items, 'total': total, 'zones': zones
    })


def payment_success(request):
    """
    Point d'entrée legacy (conservé pour compatibilité).
    Si une order_id est connue en session, redirige vers cashpay_payment_page.
    Sinon affiche la page d'échec (pas de vérification possible).
    """
    order_id = request.session.get('last_order_id')
    if order_id:
        return redirect(reverse('orders:cashpay_payment_page', kwargs={'order_id': order_id}))
    return render(request, 'orders/payment_failed.html')


def cashpay_payment_page(request, order_id):
    """
    Page relay Venus Luna (Onglet 1) :
    - Affiche la commande et le bouton « Payer avec CashPay ».
    - Au clic utilisateur, CashPay s'ouvre dans un nouvel onglet (Onglet 2).
    - L'onglet Venus Luna affiche immédiatement « Paiement en attente ».
    - Lance le polling toutes les 3s vers cashpay_payment_status.
    - Dès que le paiement est confirmé, bascule automatiquement vers la confirmation.
    """
    try:
        order = Order.objects.get(pk=order_id)
    except Order.DoesNotExist:
        raise Http404("Commande introuvable.")

    if not _can_access_order(request, order):
        if not request.user.is_authenticated:
            return redirect(f"{reverse('accounts:login')}?next={request.path}")
        raise Http404("Accès non autorisé à cette commande.")

    from django.core import signing
    token = signing.dumps(order.id, salt='cashpay-return')

    # Si le paiement est déjà confirmé, redirection directe vers la confirmation
    if order.payment_status:
        return redirect(
            reverse('orders:cashpay_return', kwargs={'order_id': order_id}) + f"?token={token}"
        )

    # Nouvelle tentative de génération du lien CashPay sur la même commande (sans doublon)
    if request.method == 'POST' and order.status == 'pending' and not order.payment_url:
        from django.db import connection
        lock_acquired = True
        use_pg_lock = connection.vendor == 'postgresql'
        if use_pg_lock:
            with connection.cursor() as cursor:
                cursor.execute("SELECT pg_try_advisory_lock(%s)", [int(order.id)])
                lock_acquired = bool(cursor.fetchone()[0])

        if not lock_acquired:
            messages.warning(
                request,
                "Une initialisation ou vérification du paiement est déjà en cours pour cette commande."
            )
            return redirect(reverse('orders:cashpay_payment_page', kwargs={'order_id': order_id}))

        try:
            order.refresh_from_db()
            if order.payment_status:
                return redirect(
                    reverse('orders:cashpay_return', kwargs={'order_id': order_id}) + f"?token={token}"
                )
            if order.status != 'pending':
                return redirect(reverse('orders:cashpay_payment_page', kwargs={'order_id': order_id}))

            if order.paygate_tx_id:
                # Une référence existe déjà : vérifier son statut sans jamais créer une 2e transaction.
                try:
                    status_res = _cashpay_fallback_check(order, order.paygate_tx_id, channel='retry_check')
                    if status_res == 'paid':
                        return redirect(
                            reverse('orders:cashpay_return', kwargs={'order_id': order_id}) + f"?token={token}"
                        )
                    from .cashpay_service import CashPayService
                    api_data = CashPayService().get_order_status(order.paygate_tx_id)
                    recovered_url = api_data.get('bill_url') or api_data.get('payment_url')
                    if recovered_url:
                        Order.objects.filter(
                            id=order.id, payment_status=False, status='pending', payment_url__isnull=True
                        ).update(payment_url=recovered_url)
                        request.session['cashpay_bill_url'] = recovered_url
                        return redirect(reverse('orders:cashpay_payment_page', kwargs={'order_id': order_id}))
                except Exception as e:
                    logger.warning(f"Vérification référence CashPay existante #{order.id} échouée : {e}")
                messages.warning(
                    request,
                    "Une transaction CashPay existe déjà pour cette commande et est en cours de vérification."
                )
                return redirect(reverse('orders:cashpay_payment_page', kwargs={'order_id': order_id}))

            from .models import PaymentReconciliation
            has_uncertain_init = PaymentReconciliation.objects.filter(
                order=order,
                kind=PaymentReconciliation.Kind.PROVIDER_STATE,
                status=PaymentReconciliation.Status.OPEN,
                details__uncertain=True,
            ).exists()
            if has_uncertain_init:
                messages.warning(
                    request,
                    "Une tentative précédente est en attente de vérification auprès de CashPay. "
                    "Veuillez patienter ou contacter le support si le problème persiste."
                )
                return redirect(reverse('orders:cashpay_payment_page', kwargs={'order_id': order_id}))

            try:
                _initialize_cashpay_for_order(request, order)
                return redirect(reverse('orders:cashpay_payment_page', kwargs={'order_id': order_id}))
            except Exception as e:
                logger.error(f"Erreur réessai CashPay commande #{order.id} : {e}", exc_info=True)
                messages.error(
                    request,
                    "Impossible de contacter CashPay pour le moment. Veuillez réessayer dans quelques instants."
                )
        finally:
            if use_pg_lock:
                with connection.cursor() as cursor:
                    cursor.execute("SELECT pg_advisory_unlock(%s)", [int(order.id)])

    bill_url = order.payment_url or request.session.get('cashpay_bill_url') or ''

    return render(request, 'orders/cashpay_payment_page.html', {
        'order': order,
        'bill_url': bill_url,
        'signed_token': token,
    })



# =====================================================
# VÉRIFICATION DES PAIEMENTS PRESTATAIRE (CASHPAY)
# =====================================================

def _int_or_none(value):
    if value is None or value == '':
        return None
    try:
        return Decimal(str(value).strip())
    except Exception:
        return None


def _verify_paid_with_cashpay_api(order, cashpay_order_ref, channel):
    """
    Interroge GET /orders/{reference} (source faisant autorité) et vérifie l'état « Paid »,
    le montant facturé (``billed_amount`` = total ; ``amount`` = reste dû sur cet endpoint,
    cf. documentation CashPay V3.1) et la devise. Retourne (statut, montant, devise) où
    statut ∈ {'paid', 'pending', 'failed', 'expired', 'provider_state', 'unverified'}.
    """
    from .cashpay_service import CashPayService
    from .payment_processing import record_reconciliation
    from .models import PaymentReconciliation

    api_data = CashPayService().get_order_status(cashpay_order_ref)
    api_state = api_data.get('state', '')
    logger.info("CashPay API (%s) commande #%s : état=%s", channel, order.id, api_state)

    if api_state in ('Canceled', 'Error'):
        return 'failed', None, None
    if api_state == 'Expired':
        return 'expired', None, None
    if api_state in ('Partial', 'Excess', 'Reviewed', 'Refunded', 'Partial Refunded', 'Excess Refunded'):
        record_reconciliation(order.id, PaymentReconciliation.Kind.PROVIDER_STATE,
                              provider_reference=cashpay_order_ref,
                              details={'channel': channel, 'state': api_state})
        return 'provider_state', None, None
    if api_state != 'Paid':
        return 'pending', None, None

    billed = _int_or_none(api_data.get('billed_amount'))
    remaining = _int_or_none(api_data.get('amount'))
    currency = api_data.get('currency') or 'XOF'
    if billed is None or (remaining is not None and remaining != 0):
        record_reconciliation(order.id, PaymentReconciliation.Kind.AMOUNT_UNVERIFIED,
                              provider_reference=cashpay_order_ref,
                              details={'channel': channel, 'billed_amount': str(billed), 'remaining': str(remaining)})
        return 'unverified', None, None
    return 'paid', billed, currency


def _cashpay_fallback_check(order, cashpay_order_ref, channel):
    """Repli par interrogation de l'API lorsque le webhook n'est pas encore arrivé."""
    from .payment_processing import confirm_provider_payment

    status, billed, currency = _verify_paid_with_cashpay_api(order, cashpay_order_ref, channel)
    if status == 'paid':
        ok, _reason = confirm_provider_payment(
            order.id, provider_reference=cashpay_order_ref, amount=billed, currency=currency, channel=channel,
        )
        return 'paid' if ok else 'pending'
    if status == 'failed':
        # Mise à jour conditionnelle : n'écrase jamais une commande confirmée entre-temps.
        Order.objects.filter(pk=order.pk, status='pending', payment_status=False).update(status='cancelled')
    return status


def cashpay_payment_status(request, order_id):
    """
    Endpoint JSON de statut de commande pour le polling frontend Venus Luna.
    Interrogé toutes les 3 secondes par l'onglet Venus Luna pendant que CashPay est ouvert.
    Sécurisé par contrôle d'accès : _can_access_order (session/auth OU jeton signé ?token=...).

    Format de réponse JSON strict :
    - {"status": "paid", "redirect_url": "/orders/retour/<id>/?token=..."}
    - {"status": "pending"}
    - {"status": "failed"}
    - {"status": "expired"}
    """
    try:
        order = Order.objects.get(pk=order_id)
    except Order.DoesNotExist:
        return JsonResponse({'status': 'not_found'}, status=404)

    if not _can_access_order(request, order):
        return JsonResponse({'status': 'unauthorized'}, status=403)

    from django.core import signing
    token = request.GET.get('token') or signing.dumps(order.id, salt='cashpay-return')
    return_url = request.build_absolute_uri(
        reverse('orders:cashpay_return', kwargs={'order_id': order.id})
    ) + f"?token={token}"

    # 1. Source de vérité primaire : BDD (mise à jour par webhook)
    if order.payment_status:
        return JsonResponse({
            'status': 'paid',
            'redirect_url': return_url
        })

    # 2. Si statut 'pending' : interrogation API fallback CashPay
    if order.status == 'pending':
        cashpay_order_ref = request.session.get('cashpay_order_ref', '') or order.paygate_tx_id or ''
        if cashpay_order_ref:
            try:
                result = _cashpay_fallback_check(order, cashpay_order_ref, channel='status_polling')
                if result == 'paid':
                    return JsonResponse({'status': 'paid', 'redirect_url': return_url})
                if result == 'failed':
                    return JsonResponse({'status': 'failed'})
                if result == 'expired':
                    return JsonResponse({'status': 'expired'})
            except Exception as e:
                # Erreur réseau / API : la commande reste en attente, le webhook ou le
                # polling suivant prendra le relais ; un échec de confirmation interne
                # a déjà été consigné en réconciliation par confirm_provider_payment.
                logger.warning(f"CashPay API status check échoué pour #{order.id} : {e}")

    # 3. Rechargement BDD après éventuel fallback
    order.refresh_from_db()

    if order.payment_status:
        return JsonResponse({
            'status': 'paid',
            'redirect_url': return_url
        })
    elif order.status == 'pending':
        return JsonResponse({'status': 'pending'})
    elif order.status in ('cancelled', 'refunded'):
        return JsonResponse({'status': 'failed'})
    else:
        return JsonResponse({'status': 'failed'})


def cashpay_return(request, order_id):
    """
    Vue de retour CashPay — vérification CÔTÉ SERVEUR uniquement.

    Utilisée par :
    1. Le polling AJAX de cashpay_payment_page (X-Requested-With: XMLHttpRequest)
    2. La redirection directe si CashPay supporte return_url dans le futur

    Scénarios :
    - payment_status=True  → paiement confirmé par le webhook → page succès
    - payment_status=False + status='pending' → tente le fallback API CashPay ;
      si l'API confirme 'Paid', met à jour la BDD et confirme
    - Toute autre situation → paiement en attente ou échoué

    Support AJAX : renvoie JSON {paid, redirect_url} pour le polling JavaScript.
    """
    # Récupération sécurisée de la commande
    try:
        order = Order.objects.get(pk=order_id)
    except Order.DoesNotExist:
        raise Http404("Commande introuvable.")

    # Contrôle d'accès : propriétaire, invité avec session, ou staff
    if not _can_access_order(request, order):
        if not request.user.is_authenticated:
            return redirect(f"{reverse('accounts:login')}?next={request.path}")
        raise Http404("Accès non autorisé à cette commande.")

    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'

    # --- SOURCE DE VÉRITÉ PRIMAIRE : base de données (mise à jour par le webhook) ---
    if not order.payment_status and order.status == 'pending':
        # Le webhook n'est pas encore arrivé. On tente le fallback : interroger l'API CashPay directement.
        cashpay_order_ref = request.session.get('cashpay_order_ref', '') or order.paygate_tx_id or ''
        if cashpay_order_ref:
            try:
                _cashpay_fallback_check(order, cashpay_order_ref, channel='return_page')
            except Exception as api_err:
                # Le fallback API a échoué (réseau, auth, etc.) : la page d'attente reste affichée.
                logger.warning(f"CashPay API fallback échoué pour #{order.id} : {api_err}")

    # Rechargement depuis la BDD après le fallback éventuel
    order.refresh_from_db()

    # --- Décision finale basée sur la BDD ---
    if order.payment_status:
        # Paiement confirmé (webhook ou API fallback)
        # Nettoyage session/panier (idempotent)
        if request.session.session_key:
            StockReservation.objects.filter(session_key=request.session.session_key).delete()
        request.session.pop('cart', None)
        request.session.pop('cashpay_bill_url', None)
        request.session.pop('cashpay_order_ref', None)

        if is_ajax:
            return JsonResponse({
                'paid': True,
                'redirect_url': request.build_absolute_uri(
                    reverse('orders:cashpay_return', kwargs={'order_id': order_id})
                ),
            })

        return render(request, 'orders/payment_confirmed.html', {
            'order': order,
            'redirect_delay': 8,  # secondes avant redirection automatique
        })

    elif order.status == 'pending':
        # Toujours en attente (le client attend la confirmation du paiement)
        if is_ajax:
            return JsonResponse({'paid': False})
        return render(request, 'orders/waiting_confirm.html', {'order': order})

    else:
        # Commande annulée, remboursée, ou statut inattendu
        if is_ajax:
            return JsonResponse({'paid': False, 'failed': True})
        return render(request, 'orders/payment_failed.html', {'order': order})


# =====================================================
# WEBHOOK & SÉCURITÉ
# =====================================================

@csrf_exempt
def cashpay_webhook(request):
    """Webhook CashPay: reçoit un body contenant un JWT (token) et valide sa signature."""
    if request.method != 'POST':
        return HttpResponse(status=405)

    try:
        payload = request.body
        data = json.loads(payload) if payload else {}
        token = data.get('token') or data.get('Token') or data.get('jwt')
        if not token:
            logger.error(
                f"CashPay webhook: token manquant. Payload keys={list(data.keys()) if isinstance(data, dict) else type(data)}"
            )
            return HttpResponse(status=400)

        # Validation cryptographique stricte de la signature JWT (Politique Fail-Closed)
        webhook_secret = getattr(settings, 'CASHPAY_SECRET_WEBHOOK', None)
        if not webhook_secret:
            logger.critical("CashPay webhook rejeté: CASHPAY_SECRET_WEBHOOK non configuré en base/environnement.")
            return HttpResponse("Configuration webhook requise", status=503)

        try:
            import jwt
            decoded_payload = jwt.decode(token, webhook_secret, algorithms=["HS256"])
        except Exception as jwt_err:
            logger.error(f"CashPay webhook: échec de vérification de signature JWT : {jwt_err}")
            return HttpResponse("Signature invalide", status=401)

        order_reference = decoded_payload.get('order_reference')
        merchant_reference = decoded_payload.get('merchant_reference')
        state = decoded_payload.get('state')

        # merchant_reference = identifiant de commande Venus Luna (fixé à la création du lien).
        # À défaut, la référence CashPay enregistrée à la création (paygate_tx_id).
        order = None
        if merchant_reference is not None and str(merchant_reference).strip().isdigit():
            order = Order.objects.filter(id=int(str(merchant_reference).strip())).first()
        elif order_reference:
            order = Order.objects.filter(paygate_tx_id=str(order_reference).strip()[:100]).first()
        if not order:
            return HttpResponse(status=404)

        from .payment_processing import confirm_provider_payment, record_reconciliation
        from .models import PaymentReconciliation

        if state in ('Partial', 'Excess'):
            record_reconciliation(order.id, PaymentReconciliation.Kind.PROVIDER_STATE,
                                  provider_reference=order_reference or '',
                                  details={'channel': 'webhook', 'state': state})
            return JsonResponse({'received': True})

        # CashPay bill states: Paid / Partial / Excess / Pending...
        if state == 'Paid':
            currency = decoded_payload.get('currency')
            billed = _int_or_none(decoded_payload.get('billed_amount'))
            amount = _int_or_none(decoded_payload.get('amount'))
            if billed is None and amount is not None and amount == order.total:
                billed = amount
            if billed is None:
                # Montant absent ou de sémantique ambiguë (``amount`` = reste dû sur certains
                # endpoints) : vérification auprès de l'API CashPay avant toute confirmation.
                ref = order_reference or order.paygate_tx_id
                api_status = None
                if ref:
                    try:
                        api_status, billed, api_currency = _verify_paid_with_cashpay_api(order, ref, 'webhook')
                        currency = currency or api_currency
                    except Exception as api_err:
                        logger.warning(f"CashPay webhook #{order.id}: vérification API impossible : {api_err}")
                if api_status != 'paid' or billed is None:
                    record_reconciliation(order.id, PaymentReconciliation.Kind.AMOUNT_UNVERIFIED,
                                          provider_reference=order_reference or '',
                                          details={'channel': 'webhook', 'amount': str(amount),
                                                   'api_status': api_status})
                    return HttpResponse("Montant non vérifiable", status=400)

            ok, reason = confirm_provider_payment(
                order.id,
                provider_reference=order_reference or merchant_reference,
                amount=billed,
                currency=currency,
                channel='webhook',
            )
            if not ok and reason == 'amount_mismatch':
                return HttpResponse("Montant incohérent", status=400)

        return JsonResponse({'received': True})

    except Exception as e:
        logger.error(f"CashPay webhook error: {e}", exc_info=True)
        return HttpResponse(status=400)


# =====================================================
# HISTORIQUE ET CONFIRMATION
# =====================================================

def order_confirm(request, order_id):
    order = get_object_or_404(Order, pk=order_id)
    if not _can_access_order(request, order):
        if not request.user.is_authenticated:
            return redirect(f"{reverse('accounts:login')}?next={request.path}")
        raise Http404("Commande introuvable ou accès non autorisé.")
    return render(request, 'orders/confirm.html', {'order': order})


@login_required
def order_history(request):
    orders = Order.objects.filter(user=request.user).order_by('-created_at')
    return render(request, 'orders/history.html', {'orders': orders})


# =====================================================
# EXPORT PDF (FACTURE)
# =====================================================

def export_order_pdf(request, order_id):
    order = get_object_or_404(Order, id=order_id)
    if not _can_access_order(request, order):
        if not request.user.is_authenticated:
            return redirect(f"{reverse('accounts:login')}?next={request.path}")
        raise Http404("Commande introuvable ou accès non autorisé.")
    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="Facture_VenusLuna_{order.id}.pdf"'

    p = canvas.Canvas(response, pagesize=A4)
    width, height = A4

    p.setFont("Helvetica-Bold", 20)
    p.setFillColor(colors.HexColor("#1e3a8a"))
    p.drawString(50, height - 50, "VENUS LUNA")

    p.setFont("Helvetica", 10)
    p.setFillColor(colors.black)
    p.drawString(50, height - 70, "Boutique Spirituelle - Lomé, Togo")

    p.setFont("Helvetica-Bold", 14)
    p.drawString(400, height - 50, f"FACTURE N° {order.id}")

    p.line(50, height - 110, 550, height - 110)

    client_name = "Client"
    if hasattr(order, 'shipping_address'):
        client_name = order.shipping_address.full_name

    p.drawString(50, height - 130, f"Client : {client_name}")

    y = height - 200
    p.setFont("Helvetica-Bold", 12)
    p.drawString(60, y, "Article")
    p.drawString(450, y, "Prix")
    p.line(50, y-5, 550, y-5)

    p.setFont("Helvetica", 11)
    for item in order.items.all():
        y -= 25
        p.drawString(60, y, f"{item.name[:40]} x{item.quantity}")
        p.drawString(450, y, f"{item.get_cost()} F")

    y -= 40
    p.line(50, y + 20, 550, y + 20)
    p.setFont("Helvetica-Bold", 14)
    p.setFillColor(colors.HexColor("#d4af37"))
    p.drawString(300, y - 10, f"TOTAL PAYÉ : {order.total} F")

    p.showPage()
    p.save()
    return response
