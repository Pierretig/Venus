import io
import logging
from decimal import Decimal
from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string, get_template
from django.utils.html import strip_tags

from apps.products.models import Product

logger = logging.getLogger(__name__)

# --- DOCUMENTS PDF ---

def generate_order_pdf(order):
    """ Génère le contenu binaire d'un PDF pour le reçu client. """
    try:
        try:
            from xhtml2pdf import pisa
        except ImportError:
            logger.warning("xhtml2pdf indisponible: génération PDF ignorée pour la commande #%s", order.id)
            return None
        template = get_template('orders/pdf_receipt.html')
        context = {
            'order': order,
            'items': order.items.all(),
            'domain': settings.SITE_URL,
        }
        html = template.render(context)
        
        result = io.BytesIO()
        # Encodage UTF-8 indispensable pour les symboles comme 'F CFA'
        pdf = pisa.pisaDocument(io.BytesIO(html.encode("UTF-8")), result)
        
        if not pdf.err:
            return result.getvalue()
        return None
    except Exception as e:
        logger.error(f"Erreur génération PDF commande {order.id}: {str(e)}")
        return None

# --- EMAILS ---

def _send_email(subject, recipient_email, template_html, context, template_txt=None, attachments=None):
    if not recipient_email:
        return False
    try:
        html_content = render_to_string(template_html, context)
        if template_txt:
            text_content = render_to_string(template_txt, context)
        else:
            text_content = strip_tags(html_content)
        msg = EmailMultiAlternatives(
            subject=subject,
            body=text_content,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[recipient_email],
        )
        msg.attach_alternative(html_content, "text/html")
        for attachment in attachments or []:
            msg.attach(*attachment)
        msg.send(fail_silently=False)
        return True
    except Exception as exc:
        logger.error("Erreur envoi email %s: %s", subject, exc)
        return False


def send_order_pending_payment_email(order, payment_url):
    recipient_email = order.email or (order.user.email if order.user else None)
    context = {
        "order": order,
        "payment_url": payment_url,
        "site_url": settings.SITE_URL,
    }
    return _send_email(
        subject=f"Commande #{order.id} créée - finalisez votre paiement",
        recipient_email=recipient_email,
        template_html="emails/order_pending_payment.html",
        template_txt="emails/order_pending_payment.txt",
        context=context,
    )


def send_order_paid_email(order):
    recipient_email = order.email or (order.user.email if order.user else None)
    attachments = []
    if order.receipt:
        try:
            order.receipt.open("rb")
            attachments.append(
                (f"Recu_VenusLuna_{order.id}.pdf", order.receipt.read(), "application/pdf")
            )
            order.receipt.close()
        except Exception as attachment_err:
            logger.warning("Impossible d'attacher le PDF pour la commande #%s: %s", order.id, attachment_err)
    context = {"order": order, "site_url": settings.SITE_URL}
    return _send_email(
        subject=f"Paiement confirmé - commande #{order.id}",
        recipient_email=recipient_email,
        template_html="emails/order_paid.html",
        template_txt="emails/order_paid.txt",
        context=context,
        attachments=attachments,
    )


def send_order_reminder_email(order, payment_url):
    recipient_email = order.email or (order.user.email if order.user else None)
    context = {
        "order": order,
        "payment_url": payment_url,
        "site_url": settings.SITE_URL,
    }
    return _send_email(
        subject=f"Rappel: finalisez votre commande #{order.id}",
        recipient_email=recipient_email,
        template_html="emails/order_reminder.html",
        template_txt="emails/order_reminder.txt",
        context=context,
    )

# --- LOGIQUE DU PANIER (SESSION) ---

def get_cart(request):
    """ Récupère le panier de la session ou un dictionnaire vide. """
    return request.session.get("cart", {})

def add_to_cart(request, product_id, quantity=1):
    """ Ajoute un produit au panier ou augmente sa quantité. """
    cart = request.session.get("cart", {})
    p_id = str(product_id)
    
    try:
        qty = int(quantity)
    except (ValueError, TypeError):
        qty = 1

    if p_id in cart:
        # On s'assure que la structure est bien un dictionnaire
        if isinstance(cart[p_id], dict):
            cart[p_id]["quantity"] += qty
        else:
            cart[p_id] = {"quantity": qty}
    else:
        cart[p_id] = {"quantity": qty}

    request.session["cart"] = cart
    request.session.modified = True

def cart_items_detail(request):
    """ Retourne les objets produits complets et le total pour l'affichage. """
    cart = request.session.get("cart", {})
    items = []
    total = Decimal("0")
    
    for p_id, data in cart.items():
        try:
            product = Product.objects.get(pk=p_id)
            # Gestion de la structure de donnée flexible
            qty = data["quantity"] if isinstance(data, dict) else data
            subtotal = product.price * int(qty)
            total += subtotal
            items.append({
                "product": product, 
                "quantity": qty, 
                "subtotal": subtotal
            })
        except Product.DoesNotExist:
            continue
            
    return items, total

def update_cart_item(request, product_id, quantity):
    """ Modifie la quantité d'un article spécifique. """
    cart = request.session.get("cart", {})
    p_id = str(product_id)
    
    if p_id in cart:
        try:
            qty = int(quantity)
            if qty > 0:
                if isinstance(cart[p_id], dict):
                    cart[p_id]["quantity"] = qty
                else:
                    cart[p_id] = {"quantity": qty}
            else:
                del cart[p_id]
        except (ValueError, TypeError):
            pass
            
    request.session["cart"] = cart
    request.session.modified = True

def clear_cart(request):
    """ Vide totalement le panier. """
    request.session["cart"] = {}
    request.session.modified = True