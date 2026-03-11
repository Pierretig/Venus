# ...existing code...
from .models import SiteSettings, Banner, SocialLink

def global_data(request):
    """
    Context processor global pour toutes les templates.
    Fournit:
    - site_settings : instance unique de SiteSettings (ou None)
    - banners : queryset des bannières actives (limitées)
    - social_links : queryset des liens sociaux
    - debug : Booléen pour les templates (True en local, False en prod)
    """
    from django.conf import settings
    site_settings = SiteSettings.get_solo() if SiteSettings.objects.exists() else None
    banners = Banner.objects.filter(is_active=True).order_by('order')[:5]
    social_links = SocialLink.objects.all()
    return {
        "site_settings": site_settings,
        "banners": banners,
        "social_links": social_links,
        "debug": settings.DEBUG,
    }
# ...existing code...
