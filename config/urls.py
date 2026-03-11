from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.contrib.sitemaps.views import sitemap
from config.sitemaps import sitemaps

handler404 = 'apps.core.views.custom_404'

urlpatterns = [
    # 1. L'ADMINISTRATION
    path('admin/', admin.site.urls),
    
    # 2. TES APPLICATIONS
    path('', include('apps.core.urls', namespace='core')),
    path('accounts/', include('apps.accounts.urls', namespace='accounts')),
    path('products/', include('apps.products.urls', namespace='products')),
    path('orders/', include('apps.orders.urls', namespace='orders')),
    path('blog/', include('apps.blog.urls', namespace='blog')),
    path('contact/', include('apps.contact.urls', namespace='contact')),
    
    # 3. CUSTOM ADMIN DASHBOARD
    path('dashboard-admin/', include('admin_custom.urls')),
    
    # 4. SITEMAP POUR LE SEO
    path('sitemap.xml', sitemap, {'sitemaps': sitemaps}, name='django.contrib.sitemaps.views.sitemap'),
]

# En développement, servir les fichiers statiques et media localement
# En production avec WhiteNoise, les fichiers statiques sont servis automatiquement
# Les fichiers media sont servis par Cloudinary (pas besoin de les servir)
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
