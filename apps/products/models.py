from decimal import Decimal
from django.conf import settings
from django.db import models
from django.urls import reverse
from django.utils.text import slugify
from django.utils import timezone
from django.contrib.auth.models import User
from cloudinary.models import CloudinaryField


def upload_to_product_path(instance, filename):
    return f'products/{instance.__class__.__name__.lower()}/'


class Category(models.Model):
    name = models.CharField("Nom", max_length=200)
    slug = models.SlugField("Slug", max_length=200, unique=True, blank=True)
    description = models.TextField("Description", blank=True)
    order = models.PositiveIntegerField("Ordre", default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Catégorie"
        verbose_name_plural = "Catégories"
        ordering = ['order', 'name']

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)


class Product(models.Model):
    category = models.ForeignKey(Category, related_name='products', on_delete=models.SET_NULL, null=True, blank=True)
    name = models.CharField("Nom", max_length=255)
    slug = models.SlugField("Slug", max_length=255, unique=True, blank=True)
    short_description = models.TextField("Courte description", max_length=500, blank=True)
    description = models.TextField("Description complète", blank=True)
    
    # Prix adaptés au FCFA
    price = models.DecimalField("Prix actuel (FCFA)", max_digits=10, decimal_places=0, default=0)
    old_price = models.DecimalField("Prix barré (FCFA)", max_digits=10, decimal_places=0, null=True, blank=True)
    
    is_active = models.BooleanField("Publié / Disponible", default=True)
    stock = models.IntegerField("Stock", default=0)
    featured = models.BooleanField("Mis en avant", default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Produit"
        verbose_name_plural = "Produits"
        ordering = ['-featured', '-created_at']

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse('products:product_detail', args=[self.slug])

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)


class ProductImage(models.Model):
    product = models.ForeignKey(Product, related_name='images', on_delete=models.CASCADE)
    image = CloudinaryField('product_image', folder='products')
    alt_text = models.CharField("Texte alternatif", max_length=255, blank=True)
    is_main = models.BooleanField("Image principale", default=False)
    order = models.PositiveSmallIntegerField("Ordre", default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Image produit"
        verbose_name_plural = "Images produit"
        ordering = ['order', 'created_at']

    def __str__(self):
        return f"Image de {self.product.name}"


class Wishlist(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='wishlist')
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    added_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Liste de souhaits"
        verbose_name_plural = "Listes de souhaits"
        unique_together = ('user', 'product')

    def __str__(self):
        return f"{self.user.username} - {self.product.name}"
