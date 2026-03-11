# filepath: c:\xampp\site_spirituel\apps\blog\models.py
from django.conf import settings
from django.db import models
from django.urls import reverse
from django.utils.text import slugify
from cloudinary.models import CloudinaryField

class Post(models.Model):
    title = models.CharField("Titre", max_length=200)
    slug = models.SlugField("Slug", max_length=200, unique=True, blank=True)
    content = models.TextField("Contenu")
    image = CloudinaryField('image', blank=True, null=True)
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        verbose_name="Auteur"
    )
    published = models.BooleanField("Publié", default=False)
    created_at = models.DateTimeField("Date de création", auto_now_add=True)
    updated_at = models.DateTimeField("Dernière modification", auto_now=True)

    class Meta:
        verbose_name = "Article"
        verbose_name_plural = "Articles"
        ordering = ['-created_at']

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        # Corrigé pour correspondre au nom de la vue dans urls.py
        return reverse('blog:detail', args=[self.id])

    def save(self, *args, **kwargs):
        # Génération automatique du slug si vide
        if not self.slug:
            base = slugify(self.title)[:180]
            slug = base
            counter = 1
            # Vérifie l'unicité du slug
            while Post.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                slug = f"{base}-{counter}"
                counter += 1
            self.slug = slug
        super().save(*args, **kwargs)