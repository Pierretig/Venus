from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.models import User
from django.db.models import Sum, Count, Q  # Ajout de Q pour la recherche
from django.db.models.functions import TruncDay
from django.utils import timezone
from datetime import timedelta
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger

# Import des modèles
from .models import Product, Category, Wishlist
from apps.orders.models import Order, OrderItem

# --- VUE : TABLEAU DE BORD ADMIN ---
@user_passes_test(lambda u: u.is_staff)
def admin_dashboard(request):
    # 1. Statistiques Globales
    total_orders = Order.objects.count()
    # On filtre sur 'delivered' pour le revenu réel
    total_revenue = Order.objects.filter(status='delivered').aggregate(Sum('total'))['total__sum'] or 0
    total_customers = User.objects.filter(is_staff=False).count()
    pending_orders = Order.objects.filter(status='pending').count()
    
    # 2. Données pour le Graphique de Ventes (7 derniers jours)
    last_week = timezone.now() - timedelta(days=7)
    sales_data = (
        Order.objects.filter(created_at__gte=last_week, status='delivered')
        .annotate(day=TruncDay('created_at'))
        .values('day')
        .annotate(daily_total=Sum('total'))
        .order_by('day')
    )
    chart_labels = [data['day'].strftime('%d %b') for data in sales_data]
    chart_values = [float(data['daily_total']) for data in sales_data]

    # 3. Données pour le Diagramme Circulaire (Top Catégories)
    category_data = (
        OrderItem.objects.filter(order__status='delivered')
        .values('product__category__name')
        .annotate(count=Count('id'))
        .order_by('-count')
    )
    pie_labels = [item['product__category__name'] or "Sans catégorie" for item in category_data]
    pie_values = [item['count'] for item in category_data]
    
    # 4. Liste des 5 dernières commandes
    recent_orders = Order.objects.all().order_by('-created_at')[:5]
    
    context = {
        'total_orders': total_orders,
        'total_revenue': total_revenue,
        'total_customers': total_customers,
        'pending_orders': pending_orders,
        'recent_orders': recent_orders,
        'chart_labels': chart_labels,
        'chart_values': chart_values,
        'pie_labels': pie_labels,
        'pie_values': pie_values,
        'today': timezone.now(),
    }
    return render(request, 'admin_custom/dashboard.html', context)

# --- VUES CLIENTS : WISHLIST & PRODUITS ---

@login_required
def toggle_wishlist(request, product_id):
    product = get_object_or_404(Product, id=product_id)
    # Correction : on vérifie si l'item existe déjà pour cet utilisateur
    wish_item = Wishlist.objects.filter(user=request.user, product=product).first()
    
    if wish_item:
        wish_item.delete() 
    else:
        Wishlist.objects.create(user=request.user, product=product)
        
    return redirect(request.META.get('HTTP_REFERER', 'products:list'))

@login_required
def wishlist_detail(request):
    items = Wishlist.objects.filter(user=request.user).select_related('product')
    return render(request, 'products/wishlist.html', {'items': items})

def category_detail(request, slug):
    category = get_object_or_404(Category, slug=slug)
    descendant_cats = category.get_descendants(include_self=True)
    products = Product.objects.filter(is_active=True, category__in=descendant_cats)
    
    # Pagination
    page_number = request.GET.get('page')
    paginator = Paginator(products, 50)
    try:
        products = paginator.page(page_number)
    except (EmptyPage, PageNotAnInteger):
        products = paginator.page(1)
    
    # Wishlist
    wishlist_ids = []
    if request.user.is_authenticated:
        wishlist_ids = Wishlist.objects.filter(user=request.user).values_list('product_id', flat=True)
    
    context = {
        'categories': Category.objects.filter(parent=None),
        'products': products,
        'wishlist_ids': wishlist_ids,
        'selected_category': category,
        'sort': 'relevance',
    }
    return render(request, 'products/product_list.html', context)

def product_list(request):
    # Catégories principales seulement (pour display)
    categories = Category.objects.filter(parent=None).prefetch_related('children__children')
    
    products = Product.objects.filter(is_active=True)
    
    # --- LOGIQUE DE RECHERCHE ---
    query = request.GET.get('q')
    if query:
        products = products.filter(
            Q(name__icontains=query) | 
            Q(description__icontains=query) |
            Q(category__name__icontains=query)
        )

    # --- FILTRE HIÉRARCHIQUE PAR CATÉGORIE ---
    category_slug = request.GET.get('category')
    selected_category = None
    if category_slug:
        selected_category = get_object_or_404(Category, slug=category_slug)
        descendant_cats = selected_category.get_descendants(include_self=True)
        products = products.filter(category__in=descendant_cats)

    sort = request.GET.get('sort', 'relevance')
    if sort == 'price_asc':
        products = products.order_by('price', '-featured', '-created_at')
    elif sort == 'price_desc':
        products = products.order_by('-price', '-featured', '-created_at')
    elif sort == 'newest':
        products = products.order_by('-created_at')
    
    # --- PAGINATION ---
    page_number = request.GET.get('page')
    paginator = Paginator(products, 50)
    try:
        products = paginator.page(page_number)
    except (EmptyPage, PageNotAnInteger):
        products = paginator.page(1)
    
    # --- GESTION DE LA WISHLIST (ICÔNES CŒUR) ---
    wishlist_ids = []
    if request.user.is_authenticated:
        # On récupère les IDs des produits déjà en wishlist
        wishlist_ids = Wishlist.objects.filter(user=request.user).values_list('product_id', flat=True)
    
    return render(request, 'products/product_list.html', {
        'categories': categories,
        'products': products,
        'wishlist_ids': wishlist_ids,
        'selected_category': selected_category,
        'sort': sort,
    })

def product_detail(request, slug):
    product = get_object_or_404(Product, slug=slug, is_active=True)
    related_products = Product.objects.filter(category=product.category).exclude(slug=slug)[:4]
    
    return render(request, 'products/product_detail.html', {
        'product': product,
        'related_products': related_products
    })