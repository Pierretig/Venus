"""
Configuration des sitemaps pour le SEO de Venus Luna
"""
from django.contrib.sitemaps import Sitemap
from django.shortcuts import reverse
from apps.products.models import Product, Category
from apps.blog.models import Post


class StaticViewSitemap(Sitemap):
    """Sitemap pour les pages statiques"""
    
    def items(self):
        return [
            'home',
            'products:list',
            'blog:list',
            'contact',
            'about',
            'faq',
            'cgv',
            'privacy',
        ]
    
    def location(self, item):
        return reverse(item)


class ProductSitemap(Sitemap):
    """Sitemap pour les produits"""
    changefreq = "weekly"
    priority = 0.9
    
    def items(self):
        return Product.objects.filter(is_active=True)
    
    def lastmod(self, obj):
        return obj.updated_at


class CategorySitemap(Sitemap):
    """Sitemap pour les catégories"""
    changefreq = "monthly"
    priority = 0.7
    
    def items(self):
        return Category.objects.all()


class BlogSitemap(Sitemap):
    """Sitemap pour les articles du blog"""
    changefreq = "monthly"
    priority = 0.8
    
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

