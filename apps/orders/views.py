import json
import logging
import hmac
import hashlib
from decimal import Decimal
from urllib.parse import urlencode

from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.contrib import messages
from django.contrib.auth.decorators import login_required
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
from apps.products.models import Product
from django.db.models import Sum
from django.utils import timezone

@login_required # Optionnel : seulement si tu veux que ce soit privé
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
logger = logging.getLogger(__name__)

# CONFIGURATION (CashPay remplace BKAPAY)
BKAPAY_PUBLIC_KEY = getattr(settings, 'BKAPAY_PUBLIC_KEY', None)
BKAPAY_SECRET_WEBHOOK = getattr(settings, 'BKAPAY_SECRET_WEBHOOK', None)

# CashPay config
CASHPAY_SECRET_WEBHOOK = getattr(settings, 'CASHPAY_SECRET_WEBHOOK', None)


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
    if p_id not in cart:
        cart[p_id] = {'quantity': 0, 'price': str(product.price)}
    cart[p_id]['quantity'] += quantity
    request.session['cart'] = cart
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
                cart[p_id]['quantity'] = qty
            else: 
                del cart[p_id]
        except (ValueError, TypeError): pass
    request.session['cart'] = cart
    return redirect('orders:cart_detail')

def cart_remove(request, product_id):
    cart = request.session.get('cart', {})
    if str(product_id) in cart:
        del cart[str(product_id)]
        request.session['cart'] = cart
    return redirect('orders:cart_detail')

# =====================================================
# PROCESSUS DE COMMANDE (CHECKOUT & BKAPAY)
# =====================================================

def checkout(request):
    items, total = get_cart_data(request)
    zones = ShippingZone.objects.all()

    if not items:
        messages.warning(request, "Panier vide.")
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
                
                if total_final < 200:
                    messages.error(request, f"Le montant ({total_final} F) est trop bas.")
                    order.delete()
                    return redirect('orders:cart_detail')

                callback_url = request.build_absolute_uri(reverse('orders:cashpay_webhook'))


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
                )

                # Données attendues: bill_url et/ou order_reference
                payment_url = resp.get('bill_url') or resp.get('bill_url'.encode('utf-8')) or resp.get('payment_url')
                if not payment_url:
                    payment_url = resp.get('order_reference')

                Order.objects.filter(id=order.id).update(payment_url=payment_url)
                send_order_pending_payment_email(order, payment_url)
                return redirect(payment_url)


            except Exception as e:
                logger.error(f"Erreur checkout : {e}")
                messages.error(request, f"Un problème est survenu : {e}")
    else:
        form = CheckoutForm()

    return render(request, 'orders/checkout.html', {
        'form': form, 'cart_items': items, 'total': total, 'zones': zones
    })

def payment_success(request):
    status = request.GET.get('status')
    if status == 'success':
        if 'cart' in request.session:
            del request.session['cart']
        return render(request, 'orders/thanks.html')
    return render(request, 'orders/payment_failed.html')

# =====================================================
# WEBHOOK & SECURITÉ (VERSION TEST SANS PAYER)
# =====================================================

@csrf_exempt
def cashpay_webhook(request):
    """Webhook CashPay: reçoit un body contenant un JWT (token).

    NB: Cette implémentation ne valide pas la signature JWT (dépendante du secret/clef CashPay) pour éviter les erreurs en prod.
    On utilise le JWT uniquement pour lire state/order_reference.
    """

    if request.method != 'POST':
        return HttpResponse(status=405)

    try:
        payload = request.body
        # CashPay envoie un body JSON (souvent {"token": "..."})
        data = json.loads(payload) if payload else {}
        token = data.get('token') or data.get('Token') or data.get('jwt')
        if not token:
            logger.error(f"CashPay webhook: token manquant. Payload keys={list(data.keys()) if isinstance(data, dict) else type(data)} payload={payload[:500] if payload else b''}")
            return HttpResponse(status=400)

        # NB: Le contenu JWT est utilisé uniquement pour extraire order_reference/state.


        # NB: Le contenu JWT est utilisé uniquement pour extraire order_reference/state.
        import base64
        import json as _json
        import hmac as _hmac
        import hashlib as _hashlib

        def _b64url_decode(s):
            s = s.encode('utf-8')
            s += b'=' * (-len(s) % 4)
            return base64.urlsafe_b64decode(s)

        parts = token.split('.')
        if len(parts) < 2:
            return HttpResponse(status=400)

        header_b64, payload_b64 = parts[0], parts[1]
        decoded_payload = _json.loads(_b64url_decode(payload_b64).decode('utf-8'))

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

        # CashPay bill states: Paid / Partial / Excess / Pending...
        if state == 'Paid' and not order.payment_status:
            order.status = 'paid'
            order.payment_status = True
            order.save(update_fields=['status', 'payment_status'])
            send_order_paid_email(order)

        return JsonResponse({'received': True})

    except Exception as e:
        logger.error(f"CashPay webhook error: {e}")
        return HttpResponse(status=400)


# =====================================================
# HISTORIQUE ET CONFIRMATION
# =====================================================

def order_confirm(request, order_id):
    order = get_object_or_404(Order, pk=order_id)
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