import json
import logging
import hmac
import hashlib
from decimal import Decimal
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
            try:
                zone_id = request.POST.get('shipping_zone')
                shipping_price = Decimal("0")
                if zone_id:
                    try:
                        zone = ShippingZone.objects.get(pk=zone_id)
                        shipping_price = zone.price
                    except (ShippingZone.DoesNotExist, ValueError):
                        shipping_price = Decimal("0")

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
                total_final = order.total

                ShippingAddress.objects.create(
                    order=order,
                    full_name=form.cleaned_data['full_name'],
                    address=form.cleaned_data['address'],
                    phone=form.cleaned_data.get('phone', ''),
                    city=form.cleaned_data.get('city', 'Lomé'),
                    country=form.cleaned_data.get('country', 'Togo')
                )

                # Mémoriser l'ID de la commande en session pour permettre l'accès légitime aux invités
                request.session['last_order_id'] = order.id

                if total_final < 200:
                    messages.error(request, f"Le montant ({total_final} F) est trop bas.")
                    order.delete()
                    return redirect('orders:cart_detail')

                callback_url = getattr(settings, 'CASHPAY_WEBHOOK_URL', None) or request.build_absolute_uri(reverse('orders:cashpay_webhook'))

                # Token signé pour authentifier le retour CashPay de manière infaillible
                from django.core import signing
                token = signing.dumps(order.id, salt='cashpay-return')
                redirect_url = request.build_absolute_uri(
                    reverse('orders:cashpay_return', kwargs={'order_id': order.id})
                ) + f"?token={token}"

                # --- CashPay: Link2Pay ---
                from .cashpay_service import CashPayService

                cashpay = CashPayService()
                if not cashpay.is_configured():
                    raise RuntimeError("CashPay n'est pas configuré (CASHPAY_* manquantes).")

                # S'assurer que le numéro de téléphone commence par '+'
                raw_phone = (order.shipping_address.phone if hasattr(order, 'shipping_address') else '') or ''
                phone_formatted = raw_phone.strip()
                if phone_formatted and not phone_formatted.startswith('+'):
                    phone_formatted = f"+{phone_formatted}"

                resp = cashpay.create_link2pay_order(
                    amount=order.total,
                    currency='XOF',
                    merchant_reference=str(order.id),
                    description=f"Commande #{order.id} Venus Luna",
                    callback_url=callback_url,
                    phone=phone_formatted,
                    type_notif=["SMS", "MAIL"],
                    redirect_url=redirect_url,
                )

                # bill_url : URL de la facture CashPay
                # order_reference : référence interne CashPay (pour le polling API fallback)
                payment_url = resp.get('bill_url') or resp.get('payment_url')
                cashpay_order_ref = resp.get('order_reference', '')

                if not payment_url:
                    raise RuntimeError("CashPay n'a pas retourné de bill_url dans la réponse.")

                Order.objects.filter(id=order.id).update(
                    payment_url=payment_url,
                    paygate_tx_id=cashpay_order_ref or None
                )
                send_order_pending_payment_email(order, payment_url)

                # Mémoriser en session pour la page relay
                request.session['cashpay_bill_url'] = payment_url
                request.session['cashpay_order_ref'] = cashpay_order_ref

                # Redirection vers la page de paiement Venus Luna (l'onglet principal restant ouvert)
                return redirect(reverse('orders:cashpay_payment_page', kwargs={'order_id': order.id}))

            except Exception as e:
                logger.error(f"Erreur checkout : {e}", exc_info=True)
                messages.error(
                    request,
                    "Un problème est survenu lors de l'initialisation du paiement. "
                    "Veuillez réessayer dans quelques instants ou contacter notre service client."
                )
    else:
        form = CheckoutForm()

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

    bill_url = request.session.get('cashpay_bill_url') or order.payment_url or ''

    return render(request, 'orders/cashpay_payment_page.html', {
        'order': order,
        'bill_url': bill_url,
        'signed_token': token,
    })


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
                from .cashpay_service import CashPayService
                cashpay = CashPayService()
                api_data = cashpay.get_order_status(cashpay_order_ref)
                api_state = api_data.get('state', '')
                logger.info(
                    f"CashPay API status check pour commande #{order.id} "
                    f"(ref={cashpay_order_ref}) : état={api_state}"
                )
                if api_state == 'Paid':
                    order.status = 'paid'
                    order.payment_status = True
                    order.save(update_fields=['status', 'payment_status'])
                    send_order_paid_email(order)
                    return JsonResponse({
                        'status': 'paid',
                        'redirect_url': return_url
                    })
                elif api_state in ('Canceled', 'Error'):
                    order.status = 'cancelled'
                    order.save(update_fields=['status'])
                    return JsonResponse({'status': 'failed'})
                elif api_state == 'Expired':
                    return JsonResponse({'status': 'expired'})
            except Exception as e:
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
                from .cashpay_service import CashPayService
                cashpay = CashPayService()
                api_data = cashpay.get_order_status(cashpay_order_ref)
                api_state = api_data.get('state', '')
                logger.info(
                    f"CashPay API fallback pour commande #{order.id} "
                    f"(ref={cashpay_order_ref}) : état={api_state}"
                )
                # Si l'API confirme le paiement, on met à jour la BDD
                # (le webhook devrait arriver aussi, mais on ne l'attend pas)
                if api_state == 'Paid':
                    order.status = 'paid'
                    order.payment_status = True
                    order.save(update_fields=['status', 'payment_status'])
                    send_order_paid_email(order)
                    logger.info(
                        f"Commande #{order.id} confirmée via API CashPay fallback (ref={cashpay_order_ref})"
                    )
            except Exception as api_err:
                # Le fallback API a échoué (réseau, auth, etc.) : on continue sans planter
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
                f"CashPay webhook: token manquant. Payload keys={list(data.keys()) if isinstance(data, dict) else type(data)} "
                f"payload={payload[:500] if payload else b''}"
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

        # Tentative de récupération de l'Order via merchant_reference (qui on a mis = order.id)
        order = None
        order_id = None
        for candidate in (merchant_reference, order_reference):
            if candidate is None:
                continue
            # candidate peut être string/num
            s = str(candidate)
            if s.isdigit():
                order_id = int(s)
                break

        if order_id is not None:
            try:
                order = Order.objects.get(id=order_id)
            except Order.DoesNotExist:
                order = None

        if not order:
            return HttpResponse(status=404)

        # Vérification du montant payé si transmis dans le payload
        payload_amount = decoded_payload.get('amount')
        if payload_amount is not None:
            try:
                if int(Decimal(str(payload_amount))) < int(order.total):
                    logger.error(
                        f"CashPay webhook: Montant insuffisant pour la commande #{order.id}. "
                        f"Reçu: {payload_amount}, Attendu: {order.total}"
                    )
                    return HttpResponse("Montant incohérent", status=400)
            except Exception as amount_err:
                logger.warning(f"CashPay webhook: Erreur lors de la comparaison de montant : {amount_err}")

        # CashPay bill states: Paid / Partial / Excess / Pending...
        if state == 'Paid' and not order.payment_status:
            order.status = 'paid'
            order.payment_status = True
            order.save(update_fields=['status', 'payment_status'])
            send_order_paid_email(order)

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
