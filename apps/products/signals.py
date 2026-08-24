from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.db.models import Avg, Count
from .models import Review, Product

def update_product_rating_stats(product):
    """
    Recalcule la note moyenne et le nombre d'avis validés pour un produit donné
    et met à jour la base de données de manière optimisée.
    """
    approved_reviews = product.reviews.filter(is_approved=True)
    stats = approved_reviews.aggregate(avg=Avg('rating'), count=Count('id'))
    
    avg_val = stats['avg'] or 0.00
    count_val = stats['count'] or 0
    
    # On utilise .update() pour modifier uniquement les champs de cache
    # et éviter de déclencher inutilement la méthode save() complète du Produit
    Product.objects.filter(pk=product.pk).update(
        average_rating=avg_val,
        total_reviews=count_val
    )

@receiver(post_save, sender=Review)
def review_saved(sender, instance, **kwargs):
    """Déclenché lors de la création, modification ou modération d'un avis."""
    if instance.product_id is None:
        return
    update_product_rating_stats(instance.product)

@receiver(post_delete, sender=Review)
def review_deleted(sender, instance, **kwargs):
    """Déclenché lors de la suppression d'un avis."""
    if instance.product_id is None:
        return
    update_product_rating_stats(instance.product)
