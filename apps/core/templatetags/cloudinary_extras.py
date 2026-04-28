"""
Template tags pour sécuriser l'affichage des images Cloudinary.
"""

from django import template
from django.urls import reverse

register = template.Library()


@register.simple_tag
def protected_image(instance, field_name='image'):
    """
    Génère une URL interne vers la vue proxy `serve_image`.
    Le public_id Cloudinary n'est JAMAIS exposé dans le HTML.

    Usage :
        {% protected_image product.images.first 'image' %}
        {% protected_image post 'image' %}
        {% protected_image user.profile 'avatar' %}
        {% protected_image banner 'image' %}
        {% protected_image site_settings 'logo' %}

    Retourne une chaîne vide si l'instance n'a pas de PK.
    """
    if not instance or not hasattr(instance, 'pk') or not instance.pk:
        return ''

    app_label = instance._meta.app_label
    model_name = instance._meta.model_name

    try:
        return reverse('core:serve_image', kwargs={
            'app_label': app_label,
            'model_name': model_name,
            'pk': instance.pk,
            'field_name': field_name,
        })
    except Exception:
        return ''


@register.simple_tag
def protected_image_or_static(instance, field_name='image', static_fallback=None):
    """
    Pareil que `protected_image`, mais retourne une URL statique de fallback
    si l'instance est vide ou le champ inexistant.

    Usage :
        {% protected_image_or_static product.images.first 'image' 'img/aze1.png' %}
    """
    if not instance or not hasattr(instance, 'pk') or not instance.pk:
        from django.templatetags.static import static as _static
        return _static(static_fallback) if static_fallback else ''

    # Vérifier que le champ contient bien une image
    field = getattr(instance, field_name, None)
    if not field:
        from django.templatetags.static import static as _static
        return _static(static_fallback) if static_fallback else ''

    app_label = instance._meta.app_label
    model_name = instance._meta.model_name

    try:
        return reverse('core:serve_image', kwargs={
            'app_label': app_label,
            'model_name': model_name,
            'pk': instance.pk,
            'field_name': field_name,
        })
    except Exception:
        from django.templatetags.static import static as _static
        return _static(static_fallback) if static_fallback else ''

