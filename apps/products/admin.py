from django.contrib import admin
from django.utils.html import format_html

from .models import (
    Category, Product, ProductAuditLog, ProductImage, Wishlist,
    StockMovement, StockReservation, AdminNotification,
)


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


class StockMovementInline(admin.TabularInline):
    model = StockMovement
    fields = ("created_at", "movement_type", "quantity", "user", "order", "comment")
    readonly_fields = ("created_at",)
    extra = 0
    can_delete = False
    show_change_link = True


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
            "fields": (
                ("price", "old_price"),
                "stock",
                "low_stock_threshold",
                "restocking_date",
            ),
        }),
("Métadonnées", {
            "fields": ("created_at", "updated_at"),
            "classes": ("collapse",),
        }),
    )

    readonly_fields = ("created_at", "updated_at")
    inlines = [ProductImageInline, ProductAuditLogInline, StockMovementInline]

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
        # IMPORTANT: en production, une erreur dans l'audit ne doit pas empêcher l'enregistrement du Product.
        def safe_create_audit(**kwargs):
            try:
                ProductAuditLog.objects.create(**kwargs)
            except Exception:
                # On ignore les erreurs d'audit (JSONField/meta, contraintes, etc.)
                return None

        # Audit CREATE
        if not change:
            safe_create_audit(
                product=obj,
                user=request.user if request.user.is_authenticated else None,
                action_type=ProductAuditLog.ActionType.CREATED,
                description="Produit créé",
                meta={},
            )
            return super().save_model(request, obj, form, change)

        # Pour un UPDATE : on compare l'ancien état
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

        # Si seulement is_active a changé, on logge comme statut changé, sinon UPDATED/OTHER
        status_changed = (before.get("is_active") != after.get("is_active"))
        if status_changed:
            safe_create_audit(
                product=obj,
                user=request.user if request.user.is_authenticated else None,
                action_type=ProductAuditLog.ActionType.STATUS_CHANGED,
                description=f"Statut du produit: {before.get('is_active')} → {after.get('is_active')}",
                meta={"changes": changes},
            )
        else:
            if changes:
                safe_create_audit(
                    product=obj,
                    user=request.user if request.user.is_authenticated else None,
                    action_type=ProductAuditLog.ActionType.UPDATED,
                    description="Produit modifié",
                    meta={"changes": changes},
                )
            else:
                safe_create_audit(
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


# --- ADMIN : GESTION DES STOCKS ---

@admin.register(StockMovement)
class StockMovementAdmin(admin.ModelAdmin):
    list_display = ("product", "movement_type", "quantity", "created_at", "user", "order_id")
    list_filter = ("movement_type", "created_at")
    search_fields = ("product__name", "comment")
    readonly_fields = ("product", "quantity", "movement_type", "created_at", "user", "order")
    fieldsets = (
        (None, {
            "fields": ("product", "movement_type", "quantity", "created_at", "user", "order", "comment")
        }),
    )

    def order_id(self, obj):
        return obj.order_id if obj.order else "-"
    order_id.short_description = "Commande #"


@admin.register(StockReservation)
class StockReservationAdmin(admin.ModelAdmin):
    list_display = ("product", "session_key", "quantity", "expires_at", "is_expired_display")
    list_filter = ("expires_at",)
    search_fields = ("product__name", "session_key")
    readonly_fields = ("product", "session_key", "quantity", "created_at", "expires_at")

    def is_expired_display(self, obj):
        return "Expirée" if obj.is_expired() else "Active"
    is_expired_display.short_description = "État"


@admin.register(AdminNotification)
class AdminNotificationAdmin(admin.ModelAdmin):
    list_display = ("title", "notification_type", "is_read", "created_at")
    list_filter = ("is_read", "notification_type", "created_at")
    search_fields = ("title", "message")
    list_editable = ("is_read",)
