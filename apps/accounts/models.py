from django.conf import settings
from django.db import models
from django.dispatch import receiver
from django.db.models.signals import post_save
from cloudinary.models import CloudinaryField


class Profile(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='profile')
    phone = models.CharField("Téléphone", max_length=20, blank=True)
    address = models.TextField("Adresse", blank=True)
    avatar = CloudinaryField('avatar', blank=True, null=True)
    bio = models.TextField("Biographie", blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Profil"
        verbose_name_plural = "Profils"

    def __str__(self):
        return f"Profil de {self.user}"

@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def create_or_update_user_profile(sender, instance, created, **kwargs):
    if created:
        # On utilise get_or_create au lieu de create pour éviter les doublons
        # Cela vérifie si le profil existe déjà avant d'essayer de le créer
        Profile.objects.get_or_create(user=instance)
    else:
        # On vérifie si l'utilisateur possède bien un profil avant de sauvegarder
        # (Certains utilisateurs anciens ou importés pourraient ne pas en avoir)
        if hasattr(instance, 'profile'):
            instance.profile.save()