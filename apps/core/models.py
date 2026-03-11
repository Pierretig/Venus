from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone
from cloudinary.models import CloudinaryField


def upload_to_site_path(instance, filename):
    return f'core/{instance.__class__.__name__.lower()}/'


class SiteSettings(models.Model):
    """
    Réglages globaux du site. On empêche la création de plusieurs instances
    pour garder un seul enregistrement (singleton simple).
    """
    site_name = models.CharField("Nom du site", max_length=200, default="LE GUIDE COMPLET DE LA MÉDITATION")
    headline = models.CharField("Texte principal affiché", max_length=255, blank=True)
    address = models.CharField("Adresse", max_length=255, blank=True)
    phone_primary = models.CharField("Téléphone principal", max_length=30, blank=True)
    phone_secondary = models.CharField("Téléphone secondaire", max_length=30, blank=True)
    email = models.EmailField("Email de contact", blank=True)
    logo = CloudinaryField('logo', blank=True, null=True)
    favicon = CloudinaryField('favicon', blank=True, null=True)
    theme_primary = models.CharField("Couleur principale (hex)", max_length=7, default="#1e0b3b", help_text="Ex: #1e0b3b")
    theme_accent = models.CharField("Couleur accent (hex)", max_length=7, default="#d4af37", help_text="Ex: #d4af37")
    footer_text = models.TextField("Texte de pied de page", blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Paramètres du site"
        verbose_name_plural = "Paramètres du site"

    def __str__(self):
        return self.site_name

    def clean(self):
        # Empêcher plusieurs instances
        if not self.pk and SiteSettings.objects.exists():
            raise ValidationError("Il ne peut exister qu'une seule instance de SiteSettings.")

    @classmethod
    def get_solo(cls):
        return cls.objects.first()

class Banner(models.Model):
    """
    Bandeau / slider pour la page d'accueil ou sections marketing.
    """
    title = models.CharField("Titre", max_length=200)
    subtitle = models.CharField("Sous-titre", max_length=255, blank=True)
    image = CloudinaryField('banner_image')
    link_url = models.CharField("URL de redirection", max_length=500, blank=True)
    is_active = models.BooleanField("Actif", default=True)
    order = models.PositiveSmallIntegerField("Ordre d'affichage", default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Bannière"
        verbose_name_plural = "Bannières"
        ordering = ['order', '-created_at']

    def __str__(self):
        return f"{self.title} ({'actif' if self.is_active else 'inactif'})"

class SocialLink(models.Model):
    """
    Liens vers les réseaux / contacts du magasin.
    """
    name = models.CharField("Réseau / Nom", max_length=100)
    url = models.URLField("URL")
    icon_class = models.CharField("Classe icône (optionnel)", max_length=200, blank=True,
                                help_text="Ex: fab fa-facebook-f ou icône CSS utilisée par le front")

    class Meta:
        verbose_name = "Lien social"
        verbose_name_plural = "Liens sociaux"

    def __str__(self):
        return self.name