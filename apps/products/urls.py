from django.urls import path
from . import views

app_name = 'products'

urlpatterns = [
    # --- Dashboard Admin ---
    # Placé en haut pour éviter qu'il ne soit confondu avec un slug de produit
    path('dashboard/', views.admin_dashboard, name='admin_dashboard'),

    # --- Catégories ---
    path('categorie/<slug:slug>/', views.category_detail, name='category_detail'),
    
    # --- Produits ---
    path('', views.product_list, name='list'), 
    
    # Utilisation du SLUG pour le SEO (ex: /products/bougie-spirituelle/)
    path('produit/<slug:slug>/', views.product_detail, name='product_detail'),
    
    # --- Wishlist ---
    path('ma-wishlist/', views.wishlist_detail, name='wishlist'),
    path('wishlist/toggle/<int:product_id>/', views.toggle_wishlist, name='toggle_wishlist'),
]
