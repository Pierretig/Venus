import logging
from django.core.mail import send_mail
from django.conf import settings
from .models import AdminNotification

logger = logging.getLogger(__name__)

def trigger_low_stock_alerts(product):
    """
    Déclenche les alertes de stock faible :
    1. Notification dans le tableau de bord administrateur (AdminNotification)
    2. Email automatique à l'administrateur
    3. Log/Simule une future intégration WhatsApp
    """
    title = f"Alerte : Stock faible pour {product.name}"
    message = f"Le produit '{product.name}' (ID: {product.id}) a atteint un niveau de stock faible. Stock actuel : {product.stock} (Seuil : {product.low_stock_threshold})."
    
    # 1. Enregistrer la notification dans le tableau de bord
    try:
        AdminNotification.objects.get_or_create(
            title=title,
            notification_type='low_stock',
            defaults={
                'message': message,
                'is_read': False
            }
        )
    except Exception as e:
        logger.error(f"Erreur lors de la création de la notification admin : {e}")

    # 2. Envoyer un email automatique
    try:
        admin_emails = [email for _, email in getattr(settings, 'ADMINS', [])]
        if not admin_emails and hasattr(settings, 'DEFAULT_FROM_EMAIL'):
            admin_emails = [settings.DEFAULT_FROM_EMAIL]
            
        if admin_emails:
            send_mail(
                subject=title,
                message=message,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=admin_emails,
                fail_silently=True
            )
            logger.info(f"Email d'alerte stock faible envoyé à {admin_emails} pour {product.name}")
    except Exception as e:
        logger.error(f"Erreur lors de l'envoi de l'email d'alerte stock faible : {e}")

    # 3. Future intégration WhatsApp
    try:
        # Placeholder pour l'intégration de l'API WhatsApp (ex: Twilio ou Meta Cloud API)
        whatsapp_payload = {
            "to": getattr(settings, 'ADMIN_WHATSAPP_NUMBER', None),
            "message": f"⚠️ *Alerte Stock* ⚠️\nLe produit *{product.name}* est presque épuisé !\nStock actuel : {product.stock}"
        }
        logger.info(f"[WHATSAPP INTEGRATION STUB] Envoi d'un message WhatsApp à l'administrateur. Payload : {whatsapp_payload}")
    except Exception as e:
        logger.error(f"Erreur lors de la simulation de l'intégration WhatsApp : {e}")
