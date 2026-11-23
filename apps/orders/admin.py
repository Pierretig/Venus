from django.contrib import admin
from django.utils.html import format_html, mark_safe
from django.utils import timezone
from .models import (
    Order, OrderItem, ShippingAddress, ShippingZone,
    OutboxEvent, PaymentReconciliation, PaymentRevisionLink,
)


# --- INLINES ---

class OrderItemInline(admin.TabularInline):
    model = OrderItem
    readonly_fields = ('line_total_display',)
    fields = ('product', 'course', 'name', 'price', 'quantity', 'line_total_display')
    extra = 0

    def line_total_display(self, obj):
        return format_html('<b style="color: #001524;">{} F</b>', obj.line_total)
    line_total_display.short_description = "Sous-total"


class ShippingAddressInline(admin.StackedInline):
    model = ShippingAddress
    can_delete = False
    verbose_name_plural = 'Adresse de livraison'
    fields = ('full_name', 'phone', 'address', 'city')


# --- ADMIN MODELS ---

@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'status',
        'colored_status',
        'status_stock',
        'payment_indicator',
        'total_display',
        'view_receipt_link',
        'created_at'
    )

    list_filter = ('status', 'payment_status', 'stock_updated', 'created_at')
    search_fields = ('id', 'email', 'user__username', 'shipping_address__full_name', 'shipping_address__phone')

    fieldsets = (
        ('Informations Générales', {
            'fields': ('user', 'email', 'status', 'notes')
        }),
        ('Détails Financiers', {
            'fields': ('subtotal', 'shipping_price', 'total'),
        }),
        ('Paiement & Suivi', {
            'fields': ('payment_status', 'payment_method', 'paygate_tx_id', 'payment_url', 'receipt', 'stock_updated'),
            'classes': ('collapse',)
        }),
        ('Dates', {
            'fields': ('created_at', 'updated_at', 'paid_at')
        }),
    )

    readonly_fields = ('created_at', 'updated_at', 'paid_at', 'subtotal', 'total', 'stock_updated', 'payment_url')
    list_editable = ('status',)
    inlines = (OrderItemInline, ShippingAddressInline)
    actions = ['reprocess_stock_for_paid_orders']

    @admin.action(description="Retraiter le stock des commandes payées incomplètes")
    def reprocess_stock_for_paid_orders(self, request, queryset):
        import logging
        from .payment_processing import process_order_stock_and_fulfillment
        from django.db import transaction
        log = logging.getLogger(__name__)
        success_count = 0
        error_count = 0
        for order in queryset.filter(status='paid', stock_updated=False):
            try:
                with transaction.atomic():
                    locked = Order.objects.select_for_update().get(id=order.id)
                    if not locked.stock_updated:
                        process_order_stock_and_fulfillment(locked, captured_by=request.user)
                        update_fields = ['stock_updated']
                        if locked.paid_at is None:
                            locked.paid_at = timezone.now()
                            update_fields.append('paid_at')
                        if locked.receipt:
                            update_fields.append('receipt')
                        if locked.notes and '[ÉCHEC TRAITEMENT STOCK]' in locked.notes:
                            cleaned_lines = [
                                line for line in locked.notes.splitlines()
                                if not line.startswith('[ÉCHEC TRAITEMENT STOCK]')
                            ]
                            cleaned_lines.append("[STOCK RÉGULARISÉ AVEC SUCCÈS]")
                            locked.notes = "\n".join(cleaned_lines).strip()
                            update_fields.append('notes')
                        locked.save(update_fields=update_fields)
                        success_count += 1
            except Exception as e:
                error_count += 1
                log.error("Reprocess stock failed for order #%s: %s", order.id, e)

        if success_count:
            self.message_user(request, f"Stock mis à jour avec succès pour {success_count} commande(s).")
        if error_count:
            self.message_user(request, f"Échec pour {error_count} commande(s) (stock toujours insuffisant).", level='ERROR')

    # --- MÉTHODES D'AFFICHAGE ---

    def colored_status(self, obj):
        colors = {
            'pending': '#ffc107',
            'paid': '#28a745',
            'shipped': '#17a2b8',
            'delivered': '#001524',
            'cancelled': '#dc3545',
            'refunded': '#6f42c1',
        }
        if obj.status == 'paid' and not obj.stock_updated:
            return format_html(
                '<span style="background: #e67e22; color: white; padding: 3px 10px; border-radius: 12px; font-weight: bold; font-size: 11px;">{}</span>',
                "PAYÉ (STOCK INCOMPLET)"
            )
        return format_html(
            '<span style="background: {}; color: white; padding: 3px 10px; border-radius: 12px; font-weight: bold; font-size: 11px;">{}</span>',
            colors.get(obj.status, '#6c757d'),
            obj.get_status_display().upper()
        )
    colored_status.short_description = "Aperçu"

    def payment_indicator(self, obj):
        if obj.payment_status:
            return mark_safe('<span style="color: #28a745;">✔ Payé</span>')
        if obj.payment_url:
            return format_html('<a href="{}" target="_blank" style="color: #d4af37;">🔗 Lien envoyé</a>', obj.payment_url)
        return mark_safe('<span style="color: #dc3545;">✘ Non payé</span>')
    payment_indicator.short_description = "Paiement"

    def total_display(self, obj):
        return format_html('<b style="color: #d4af37;">{} F</b>', obj.total)
    total_display.short_description = "Total"

    def status_stock(self, obj):
        if obj.stock_updated:
            return mark_safe('<span title="Stock déduit" style="cursor:help;">✅</span>')
        if obj.status == 'paid':
            return mark_safe('<span title="Stock non déduit !" style="color: #e67e22; font-weight: bold; cursor:help;">⚠️ Incomplet</span>')
        return "-"
    status_stock.short_description = "Stk"

    def view_receipt_link(self, obj):
        if obj.receipt:
            return format_html(
                '<a href="{}" target="_blank" style="background: #001524; color: #d4af37; padding: 5px 10px; border-radius: 4px; text-decoration: none; font-size: 10px;">PDF</a>',
                obj.receipt.url
            )
        return "-"
    view_receipt_link.short_description = "Reçu"


@admin.register(ShippingZone)
class ShippingZoneAdmin(admin.ModelAdmin):
    list_display = ('name', 'price_display', 'delivery_time')
    list_editable = ('delivery_time',)

    def price_display(self, obj):
        return f"{obj.price} F"
    price_display.short_description = "Frais"


# --- PAIEMENT : RÉVISIONS ACHETÉES, RÉCONCILIATION, OUTBOX ---

class _ReadOnlyAdminMixin:
    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(PaymentRevisionLink)
class PaymentRevisionLinkAdmin(_ReadOnlyAdminMixin, admin.ModelAdmin):
    list_display = ('order', 'order_item', 'course', 'course_revision', 'source', 'captured_at')
    list_filter = ('source',)
    search_fields = ('order__id', 'course__title')
    readonly_fields = [f.name for f in PaymentRevisionLink._meta.fields]

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(PaymentReconciliation)
class PaymentReconciliationAdmin(admin.ModelAdmin):
    list_display = ('id', 'kind', 'status', 'order', 'order_item', 'occurrences', 'created_at', 'last_seen_at')
    list_filter = ('status', 'kind')
    search_fields = ('order__id', 'provider_reference')
    readonly_fields = ('order', 'order_item', 'kind', 'status', 'dedup_key', 'provider_reference', 'details',
                       'occurrences', 'created_at', 'last_seen_at', 'resolved_at', 'resolved_by')
    fields = readonly_fields + ('resolution_note',)
    actions = ['capture_published_revision', 'mark_resolved']

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    @admin.action(description="Capturer la révision publiée et attribuer l'accès (formation sans révision)")
    def capture_published_revision(self, request, queryset):
        from django.db import transaction
        from .payment_processing import capture_course_revisions
        done = 0
        for rec in queryset.filter(status=PaymentReconciliation.Status.OPEN,
                                   kind=PaymentReconciliation.Kind.NO_PUBLISHED_REVISION):
            with transaction.atomic():
                order = Order.objects.select_for_update().get(pk=rec.order_id)
                if not order.payment_status:
                    continue
                capture_course_revisions(order, source=PaymentRevisionLink.Source.RECONCILIATION,
                                         captured_by=request.user)
                if PaymentRevisionLink.objects.filter(order_item_id=rec.order_item_id).exists():
                    PaymentReconciliation.objects.filter(pk=rec.pk).update(
                        status=PaymentReconciliation.Status.RESOLVED, resolved_at=timezone.now(),
                        resolved_by=request.user,
                        resolution_note="Révision publiée capturée et accès attribué.",
                    )
                    done += 1
        self.message_user(request, f"{done} incident(s) résolu(s). Les formations toujours sans révision publiée restent ouvertes.")

    @admin.action(description="Marquer comme résolu (après traitement manuel)")
    def mark_resolved(self, request, queryset):
        n = queryset.filter(status=PaymentReconciliation.Status.OPEN).update(
            status=PaymentReconciliation.Status.RESOLVED, resolved_at=timezone.now(), resolved_by=request.user,
        )
        self.message_user(request, f"{n} incident(s) marqué(s) comme résolu(s).")


@admin.register(OutboxEvent)
class OutboxEventAdmin(admin.ModelAdmin):
    list_display = ('id', 'event_type', 'status', 'order', 'attempts', 'available_at', 'locked_until', 'processed_at')
    list_filter = ('status', 'event_type')
    search_fields = ('idempotency_key', 'order__id')
    readonly_fields = [f.name for f in OutboxEvent._meta.fields]
    actions = ['requeue_failed']

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    @admin.action(description="Remettre en file les événements en échec (FAILED)")
    def requeue_failed(self, request, queryset):
        n = queryset.filter(status=OutboxEvent.Status.FAILED).update(
            status=OutboxEvent.Status.PENDING, available_at=timezone.now(), attempts=0,
        )
        self.message_user(request, f"{n} événement(s) remis en file.")
