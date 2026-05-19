from django.urls import path
from . import views

app_name = 'orders'

urlpatterns = [
    # Panier
    path('cart/', views.cart_detail, name='cart_detail'),
    path('cart/add/<int:product_id>/', views.cart_add, name='cart_add'),
    path('cart/remove/<int:product_id>/', views.cart_remove, name='cart_remove'),
    path('cart/update/<int:product_id>/', views.cart_update, name='cart_update'),
    path('cart/count/', views.cart_count_api, name='cart_count_api'),

    # Commande et Paiement
    path('checkout/', views.checkout, name='checkout'),
    path('confirm/<int:order_id>/', views.order_confirm, name='order_confirm'),
    path('history/', views.order_history, name='order_history'),
    path('success/', views.payment_success, name='payment_success'),

    # Webhook CashPay
    path('webhook/cashpay/', views.cashpay_webhook, name='cashpay_webhook'),

    # Webhook BKApay (legacy - conservé) 
    # NB: la vue bkapay_webhook a été remplacée par cashpay_webhook. 
    # On évite toute erreur d'import en désactivant temporairement cette route.
    # path('webhook/bkapay/', views.bkapay_webhook, name='bkapay_webhook'),


    path('mon-tableau-de-bord/', views.dashboard_view, name='admin_dashboard'),

    # Factures PDF & Alias (Pour corriger l'erreur NoReverseMatch)
    path('facture/pdf/<int:order_id>/', views.export_order_pdf, name='export_pdf'),
    path('facture/download/<int:order_id>/', views.export_order_pdf, name='order_pdf'), # Ajouté
    path('facture/receipt/<int:order_id>/', views.export_order_pdf, name='download_receipt'), # Ajouté
]