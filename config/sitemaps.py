"""
Configuration des sitemaps pour le SEO de Venus Luna
"""
from django.contrib.sitemaps import Sitemap
from django.shortcuts import reverse
from apps.products.models import Product, Category
from apps.blog.models import Post


class StaticViewSitemap(Sitemap):
    """Sitemap pour les pages statiques"""
    protocol = 'https'
    # Chaque page a sa propre config SEO
    _pages = {
        'home':         {'changefreq': 'daily',   'priority': 1.0},
        'products:list':{'changefreq': 'daily',   'priority': 0.9},
        'blog:list':    {'changefreq': 'weekly',  'priority': 0.8},
        'contact':      {'changefreq': 'monthly', 'priority': 0.6},
        'about':        {'changefreq': 'monthly', 'priority': 0.6},
        'faq':          {'changefreq': 'monthly', 'priority': 0.5},
        'cgv':          {'changefreq': 'yearly',  'priority': 0.3},
        'privacy':      {'changefreq': 'yearly',  'priority': 0.3},
    }
    
    def items(self):
        return list(self._pages.keys())
    
    def location(self, item):
        return reverse(item)
    
    def changefreq(self, item):
        return self._pages[item]['changefreq']
    
    def priority(self, item):
        return self._pages[item]['priority']
    
    def lastmod(self, item):
        # Date fixe au build ; remplacée par une date réelle si tu veux
        from datetime import date
        return date.today()


class ProductSitemap(Sitemap):
    """Sitemap pour les produits"""
    protocol = 'https'
    changefreq = "weekly"
    priority = 0.9
    limit = 5000
    
    def items(self):
        return Product.objects.filter(is_active=True)
    
    def lastmod(self, obj):
        return obj.updated_at


class CategorySitemap(Sitemap):
    """Sitemap pour les catégories"""
    protocol = 'https'
    changefreq = "monthly"
    priority = 0.7
    limit = 5000
    
    def items(self):
        return Category.objects.all()
    
    def location(self, obj):
        return obj.get_absolute_url()
    
    def lastmod(self, obj):
        return obj.created_at


class BlogSitemap(Sitemap):
    """Sitemap pour les articles du blog"""
    protocol = 'https'
    changefreq = "monthly"
    priority = 0.8
    limit = 5000
    
    def items(self):
        return Post.objects.filter(published=True)
    
    def lastmod(self, obj):
        return obj.updated_at or obj.created_at


# Dictionnaire des sitemaps (utilisé dans urls.py)
sitemaps = {
    'static': StaticViewSitemap,
    'products': ProductSitemap,
    'categories': CategorySitemap,
    'blog': BlogSitemap,
}

