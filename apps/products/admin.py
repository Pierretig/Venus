from django.contrib import admin
from django.utils.html import format_html

from .models import Category, Product, ProductAuditLog, ProductImage, Wishlist


class ProductImageInline(admin.TabularInline):
    model = ProductImage
    fields = ("image", "alt_text", "is_main", "order")
    extra = 1


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    change_form_template = "admin/products/category/change_form.html"
    list_display = ("name", "parent", "order", "created_at")
    list_filter = ("parent",)
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

    def change_view(self, request, object_id=None, form_url='', extra_context=None):
        extra_context = extra_context or {}
        if object_id:
            category = self.get_object(request, object_id)
            if category:
                extra_context['add_subcategory_url'] = (
                    f"{self.get_model_perms(request)['add'] and 'add/' or ''}?parent={category.pk}"
                )
        return super().change_view(request, object_id, form_url, extra_context=extra_context)


class ProductAuditLogInline(admin.TabularInline):
    model = ProductAuditLog
    fields = ("created_at", "user", "action_type", "description")
    readonly_fields = ("created_at", "user", "action_type", "description")
    can_delete = False
    extra = 0
    show_change_link = False


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
    list_display_links = ("name",)
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
            "fields": (("price", "old_price"), "stock"),  # Met prix et prix barré sur la même ligne
        }),
        ("Métadonnées", {
            "fields": ("created_at", "updated_at"),
            "classes": ("collapse",),  # Cache cette section par défaut
        }),
    )

    readonly_fields = ("created_at", "updated_at")
    inlines = [ProductImageInline, ProductAuditLogInline]

    def display_image(self, obj):
        try:
            main_image = obj.images.filter(is_main=True).first() or obj.images.first()
            if main_image and main_image.image:
                return format_html(
                    '<img src="{}" width="50" height="50" style="object-fit: cover; border-radius: 4px;" />',
                    main_image.image.url,
                )
        except Exception:
            pass
        return "🖼️"

    display_image.short_description = "Aperçu"

    def save_model(self, request, obj, form, change):
        # Audit trail : auteur + horodatage + historique
        if not change:
            ProductAuditLog.objects.create(
                product=obj,
                user=request.user if request.user.is_authenticated else None,
                action_type=ProductAuditLog.ActionType.CREATED,
                description="Produit créé",
                meta={},
            )
            return super().save_model(request, obj, form, change)

        # Pour un UPDATE : on compare l’ancien état
        old = Product.objects.filter(pk=obj.pk).first()
        before = {}
        if old:
            before = {
                "category_id": old.category_id,
                "is_active": old.is_active,
                "featured": old.featured,
                "stock": old.stock,
                "price": str(old.price) if old.price is not None else None,
                "old_price": str(old.old_price) if old.old_price is not None else None,
            }

        super().save_model(request, obj, form, change)

        after = {
            "category_id": obj.category_id,
            "is_active": obj.is_active,
            "featured": obj.featured,
            "stock": obj.stock,
            "price": str(obj.price) if obj.price is not None else None,
            "old_price": str(obj.old_price) if obj.old_price is not None else None,
        }

        changes = {}
        for k in after.keys():
            if before.get(k) != after.get(k):
                changes[k] = {"from": before.get(k), "to": after.get(k)}

        # Si seulement is_active a changé, on logge comme statut changé, sinon UPDATED
        status_changed = (before.get("is_active") != after.get("is_active"))
        if status_changed:
            ProductAuditLog.objects.create(
                product=obj,
                user=request.user if request.user.is_authenticated else None,
                action_type=ProductAuditLog.ActionType.STATUS_CHANGED,
                description=f"Statut du produit: {before.get('is_active')} → {after.get('is_active')}",
                meta={"changes": changes},
            )
        else:
            if changes:
                ProductAuditLog.objects.create(
                    product=obj,
                    user=request.user if request.user.is_authenticated else None,
                    action_type=ProductAuditLog.ActionType.UPDATED,
                    description="Produit modifié",
                    meta={"changes": changes},
                )
            else:
                # Changement sans différences sur champs suivis (ex: ordre inline)
                ProductAuditLog.objects.create(
                    product=obj,
                    user=request.user if request.user.is_authenticated else None,
                    action_type=ProductAuditLog.ActionType.OTHER,
                    description="Produit mis à jour",
                    meta={},
                )

    def delete_model(self, request, obj):
        ProductAuditLog.objects.create(
            product=obj,
            user=request.user if request.user.is_authenticated else None,
            action_type=ProductAuditLog.ActionType.DELETED,
            description="Produit supprimé",
            meta={},
        )
        return super().delete_model(request, obj)


@admin.register(ProductImage)
class ProductImageAdmin(admin.ModelAdmin):
    list_display = ("product", "image_preview", "is_main", "order", "created_at")
    list_filter = ("is_main",)
    search_fields = ("product__name", "alt_text")

    def image_preview(self, obj):
        try:
            if obj.image:
                return format_html(
                    '<img src="{}" width="50" style="object-fit: cover;" />',
                    obj.image.url,
                )
        except Exception:
            pass
        return "Pas d'image"

    image_preview.short_description = "Aperçu"


admin.site.register(Wishlist)

