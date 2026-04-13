from django.contrib import admin
from django.utils.html import format_html
from .models import Category, Product, ProductImage, Wishlist

class ProductImageInline(admin.TabularInline):
    model = ProductImage
    fields = ("image", "alt_text", "is_main", "order")
    extra = 1

@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "parent", "order", "created_at")
    list_filter = ("parent", "is_active")
    prepopulated_fields = {"slug": ("name",)}
    search_fields = ("name", "description")
    ordering = ("parent", "order", "name")
    list_editable = ("order",)
    fieldsets = (
        ("Général", {
            "fields": ("name", "parent", "order")
        }),
        ("Description", {
            "fields": ("description",),
        }),
    )

@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    # Liste des produits
    list_display = (
        "display_image", 
        "name",
        "category",
        "price",
        "stock",
        "is_active",
        "featured",
    )
    list_editable = ("price", "stock", "is_active", "featured")
    list_filter = ("is_active", "featured", "category")
    search_fields = ("name", "short_description", "description")
    prepopulated_fields = {"slug": ("name",)}
    
    # ORGANISATION DES CHAMPS (Pour s'assurer qu'ils apparaissent tous)
    fieldsets = (
        ("Informations Générales", {
            "fields": ("name", "slug", "category", "featured", "is_active")
        }),
        ("Description du Produit", {
            "fields": ("short_description", "description"),
        }),
        ("Tarification et Stock", {
            "fields": (("price", "old_price"), "stock"), # Met prix et prix barré sur la même ligne
        }),
        ("Métadonnées", {
            "fields": ("created_at", "updated_at"),
            "classes": ("collapse",), # Cache cette section par défaut
        }),
    )

    readonly_fields = ("created_at", "updated_at")
    inlines = [ProductImageInline]

    def display_image(self, obj):
        main_image = obj.images.filter(is_main=True).first() or obj.images.first()
        if main_image and main_image.image:
            return format_html('<img src="{}" width="50" height="50" style="object-fit: cover; border-radius: 4px;" />', main_image.image.url)
        return "🖼️"
    display_image.short_description = "Aperçu"

@admin.register(ProductImage)
class ProductImageAdmin(admin.ModelAdmin):
    list_display = ("product", "image_preview", "is_main", "order", "created_at")
    list_filter = ("is_main",)
    search_fields = ("product__name", "alt_text")

    def image_preview(self, obj):
        if obj.image:
            return format_html('<img src="{}" width="50" height="50" style="object-fit: cover;" />', obj.image.url)
        return "Pas d'image"
    image_preview.short_description = "Aperçu"

admin.site.register(Wishlist)