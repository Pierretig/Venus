from django.urls import path, include, reverse_lazy
from django.contrib import admin
from django.views.generic import RedirectView
from django.conf import settings
from apps.core import views as core_views

# Base URL du domaine principal pour les redirections
site_url = settings.SITE_URL.rstrip('/')

# 1. Namespace 'core' : routes institutionnelles indispensables, proxy d'image et retour accueil boutique
core_subdomain_patterns = (
    [
        path('conditions-generales-de-vente/', core_views.cgv_view, name='cgv'),
        path('confidentialite-et-conditions/', core_views.confidentialite, name='privacy'),
        path('a-propos/', core_views.about, name='about'),
        path('foire-aux-questions/', core_views.faq, name='faq'),
        path('contact/', core_views.contact_view, name='contact'),
        path(
            'media/image/<str:app_label>/<str:model_name>/<int:pk>/<str:field_name>/',
            core_views.serve_image,
            name='serve_image',
        ),
        path(
            'boutique/',
            RedirectView.as_view(url=f"{site_url}/", permanent=False),
            name='home',
        ),
    ],
    'core',
)

# 2. Namespace 'products' : redirection vers le catalogue produits et la wishlist boutique
products_subdomain_patterns = (
    [
        path(
            '',
            RedirectView.as_view(
                url=f"{site_url}/products/",
                permanent=False,
            ),
            name='list',
        ),
        path(
            'wishlist/',
            RedirectView.as_view(
                url=f"{site_url}/products/ma-wishlist/",
                permanent=False,
            ),
            name='wishlist',
        ),
    ],
    'products',
)

# 3. Namespace 'blog' : redirection vers le blog sur le domaine principal
blog_subdomain_patterns = (
    [
        path(
            '',
            RedirectView.as_view(
                url=f"{site_url}/blog/",
                permanent=False,
            ),
            name='list',
        ),
    ],
    'blog',
)

# 4. Namespace 'admin_custom' : redirection vers le tableau de bord admin principal
admin_custom_subdomain_patterns = (
    [
        path(
            '',
            RedirectView.as_view(
                url=f"{site_url}/dashboard-admin/",
                permanent=False,
            ),
            name='dashboard',
        ),
    ],
    'admin_custom',
)

urlpatterns = [
    # Administration Django
    path('admin/', admin.site.urls),

    # Route historique directe sans namespace pour compatibilité
    path('contact/', core_views.contact_view, name='contact'),

    # Pages institutionnelles indispensables (namespace 'core')
    path('', include(core_subdomain_patterns)),

    # Gestion des comptes utilisateurs (namespace 'accounts')
    path('accounts/', include('apps.accounts.urls', namespace='accounts')),

    # Commandes et panier (namespace 'orders')
    path('orders/', include('apps.orders.urls', namespace='orders')),

    # Alias transverses vers la boutique et l'admin principal
    path('shop/', include(products_subdomain_patterns)),
    path('actualites/', include(blog_subdomain_patterns)),
    path('custom-admin/', include(admin_custom_subdomain_patterns)),

    # LMS à la racine du sous-domaine (namespace 'courses')
    # Doit être en dernier pour que les slugs de cours /<slug>/ ne masquent pas les routes ci-dessus
    path('', include('apps.courses.urls', namespace='courses')),
]
