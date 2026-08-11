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


def trigger_new_review_alerts(review):
    """
    Notifie l'administrateur lors de la soumission d'un nouvel avis.
    """
    product = review.product
    title = f"Modération : Nouvel avis client pour {product.name}"
    message = (
        f"Un nouvel avis client a été soumis pour le produit '{product.name}' et est en attente de modération.\n\n"
        f"Client : {review.client_name}\n"
        f"Note : {review.rating}/5\n"
        f"Avis : {review.title}\n"
        f"Commentaire : {review.comment}\n"
    )
    
    # 1. Envoyer un email automatique à l'admin
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
            logger.info(f"Email de notification de nouvel avis envoyé à {admin_emails}")
    except Exception as e:
        logger.error(f"Erreur lors de l'envoi de l'email de notification de nouvel avis : {e}")

    # 2. Stub WhatsApp
    try:
        whatsapp_payload = {
            "to": getattr(settings, 'ADMIN_WHATSAPP_NUMBER', None),
            "message": f"📝 *Nouvel Avis à Modérer* 📝\nProduit : *{product.name}*\nClient : {review.client_name}\nNote : {review.rating}/5\nCommentaire : {review.comment[:100]}..."
        }
        logger.info(f"[WHATSAPP INTEGRATION STUB] Notification admin nouvel avis. Payload : {whatsapp_payload}")
    except Exception as e:
        logger.error(f"Erreur WhatsApp stub : {e}")


def trigger_review_approved_alerts(review):
    """
    Notifie le client lorsque son avis est validé.
    """
    user = review.user
    if not user or not user.email:
        return
        
    product = review.product
    title = f"Votre avis sur {product.name} a été publié !"
    message = (
        f"Bonjour {review.client_name},\n\n"
        f"Nous avons le plaisir de vous informer que votre avis sur le produit '{product.name}' a été approuvé et publié.\n\n"
        f"Note : {review.rating}/5\n"
        f"Commentaire : {review.comment}\n\n"
        f"Merci pour votre confiance et votre partage !\n"
        f"L'équipe Venus Luna"
    )
    
    # 1. Envoyer un email automatique au client
    try:
        send_mail(
            subject=title,
            message=message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user.email],
            fail_silently=True
        )
        logger.info(f"Email de confirmation d'approbation d'avis envoyé à {user.email}")
    except Exception as e:
        logger.error(f"Erreur lors de l'envoi de l'email d'approbation au client : {e}")

    # 2. Stub WhatsApp
    try:
        whatsapp_payload = {
            "to": getattr(user.profile, 'phone', None) if hasattr(user, 'profile') else None,
            "message": f"✨ *Votre avis a été publié !* ✨\nMerci {review.client_name} d'avoir partagé votre avis sur *{product.name}* !"
        }
        logger.info(f"[WHATSAPP INTEGRATION STUB] Notification client avis approuvé. Payload : {whatsapp_payload}")
    except Exception as e:
        logger.error(f"Erreur WhatsApp stub : {e}")

