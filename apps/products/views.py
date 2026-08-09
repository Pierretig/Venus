from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.models import User
from django.db.models import Sum, Count, Q, F
from django.db.models.functions import TruncDay
from django.utils import timezone
from datetime import timedelta
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger

# Import des modèles
from .models import Product, Category, Wishlist, StockMovement, StockReservation, AdminNotification
from apps.orders.models import Order, OrderItem
from .stock_utils import release_expired_reservations


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
    categories = Category.objects.filter(parent=None).prefetch_related('subcategories__subcategories')

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


# --- VUE : TABLEAU DE BORD DES STOCKS ---

@user_passes_test(lambda u: u.is_staff)
def stock_dashboard(request):
    """
    Tableau de bord des stocks :
    - produits en rupture
    - produits en stock faible
    - meilleures ventes
    - produits jamais vendus
    - derniers mouvements de stock
    - alertes actives
    - principaux KPI
    """
    now = timezone.now()

    # Nettoyage opportuniste des réservations expirées (sans bloquer)
    try:
        release_expired_reservations()
    except Exception:
        pass

    # --- KPI ---
    total_products = Product.objects.filter(is_active=True).count()
    total_stock_value = Product.objects.filter(is_active=True).aggregate(
        total=Sum('stock')
    )['total'] or 0
    active_reservations = StockReservation.objects.filter(expires_at__gt=now).count()
    low_stock_count = Product.objects.filter(
        is_active=True, stock__gt=0, stock__lte=F('low_stock_threshold')
    ).count()

    # --- Produits en rupture (stock réel nul) ---
    out_of_stock = Product.objects.filter(is_active=True, stock__lte=0).order_by('-updated_at')

    # --- Produits en stock faible ---
    low_stock_products = []
    for p in Product.objects.filter(is_active=True, stock__gt=0).order_by('stock')[:50]:
        if p.stock <= p.low_stock_threshold:
            low_stock_products.append(p)

    # --- Meilleures ventes (quantités vendues cumulées) ---
    best_sellers = (
        OrderItem.objects.filter(order__payment_status=True)
        .values('product__id', 'product__name', 'product__slug')
        .annotate(total_sold=Sum('quantity'))
        .order_by('-total_sold')[:10]
    )

    # --- Produits jamais vendus ---
    sold_product_ids = OrderItem.objects.filter(order__payment_status=True).values_list('product_id', flat=True).distinct()
    never_sold = Product.objects.filter(is_active=True).exclude(id__in=sold_product_ids)[:10]

    # --- Derniers mouvements de stock ---
    recent_movements = StockMovement.objects.select_related('product', 'user', 'order')[:20]

    # --- Alertes actives (non lues) ---
    active_alerts = AdminNotification.objects.filter(is_read=False)[:20]

    context = {
        'total_products': total_products,
        'total_stock_value': total_stock_value,
        'active_reservations': active_reservations,
        'low_stock_count': low_stock_count,
        'out_of_stock': out_of_stock,
        'low_stock_products': low_stock_products,
        'best_sellers': best_sellers,
        'never_sold': never_sold,
        'recent_movements': recent_movements,
        'active_alerts': active_alerts,
        'today': now,
    }
    return render(request, 'admin_custom/stock_dashboard.html', context)
