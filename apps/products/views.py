import logging

from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.models import User
from django.db.models import Sum, Count, Q, F
from django.db.models.functions import TruncDay
from django.utils import timezone
from datetime import timedelta
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger

# Import des modèles
from .models import Product, Category, Wishlist, StockMovement, StockReservation, AdminNotification, Review
from apps.orders.models import Order, OrderItem
from .stock_utils import release_expired_reservations
from .forms import ReviewForm
from apps.core.models import SiteSettings
from django.contrib import messages
from django.utils.html import strip_tags

logger = logging.getLogger(__name__)


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


def check_verified_purchase(user, product):
    """Vérifie si l'utilisateur a acheté et payé le produit."""
    if not user.is_authenticated:
        return False
    from apps.orders.models import OrderItem
    return OrderItem.objects.filter(
        order__user=user,
        product=product,
        order__payment_status=True
    ).exists()


def product_detail(request, slug):
    product = get_object_or_404(Product, slug=slug, is_active=True)
    related_products = Product.objects.filter(category=product.category).exclude(slug=slug)[:4]

    # Récupération des avis approuvés avec jointure profil pour les avatars
    reviews_list = product.reviews.filter(is_approved=True).select_related('user__profile').order_by('-is_pinned', '-created_at')
    
    # Répartition des notes (1 à 5 étoiles)
    total_approved = reviews_list.count()
    distribution = {i: 0 for i in range(1, 6)}
    distribution_percentages = {i: 0 for i in range(1, 6)}
    if total_approved > 0:
        counts = reviews_list.values('rating').annotate(c=Count('id'))
        for item in counts:
            rating_val = item['rating']
            if 1 <= rating_val <= 5:
                distribution[rating_val] = item['c']
                distribution_percentages[rating_val] = int((item['c'] / total_approved) * 100)

    # Pagination des avis (10 par page)
    review_paginator = Paginator(reviews_list, 10)
    page_number = request.GET.get('review_page')
    try:
        reviews_paginated = review_paginator.page(page_number)
    except (EmptyPage, PageNotAnInteger):
        reviews_paginated = review_paginator.page(1)

    # Déterminer si l'utilisateur connecté peut laisser un avis
    user_has_reviewed = False
    is_buyer = False
    if request.user.is_authenticated:
        user_has_reviewed = product.reviews.filter(user=request.user).exists()
        is_buyer = check_verified_purchase(request.user, product)

    site_settings = SiteSettings.get_solo()
    reviews_only_buyers = site_settings.reviews_only_buyers if site_settings else False

    # Formulaire vide (initialisé avec le prénom du client si disponible)
    initial_data = {}
    if request.user.is_authenticated:
        initial_data['client_name'] = request.user.first_name or request.user.username
    form = ReviewForm(initial=initial_data)

    context = {
        'product': product,
        'related_products': related_products,
        'reviews': reviews_paginated,
        'total_approved_reviews': total_approved,
        'distribution': distribution,
        'distribution_percentages': distribution_percentages,
        'user_has_reviewed': user_has_reviewed,
        'is_buyer': is_buyer,
        'reviews_only_buyers': reviews_only_buyers,
        'review_form': form,
    }
    return render(request, 'products/product_detail.html', context)


def submit_review(request, product_id):
    """
    Traite la soumission d'un avis client.
    Accessible aux visiteurs connectés ET non connectés.
    """
    if request.method != 'POST':
        return redirect('products:list')

    product = get_object_or_404(Product, id=product_id, is_active=True)

    site_settings = SiteSettings.get_solo()
    reviews_only_buyers = site_settings.reviews_only_buyers if site_settings else False

    # Double sécurité pour les utilisateurs connectés : un avis unique par produit
    if request.user.is_authenticated:
        if Review.objects.filter(product=product, user=request.user).exists():
            messages.error(request, "Vous avez déjà rédigé un avis pour ce produit.")
            return redirect(product.get_absolute_url())

        is_buyer = check_verified_purchase(request.user, product)

        # Si dépôt réservé aux acheteurs vérifiés (connectés uniquement)
        if reviews_only_buyers and not is_buyer:
            messages.error(request, "Désolé, le dépôt d'avis pour ce produit est réservé aux personnes l'ayant acheté.")
            return redirect(product.get_absolute_url())
    else:
        # Visiteur anonyme : impossible de vérifier l'achat
        is_buyer = False
        if reviews_only_buyers:
            messages.error(request, "Le dépôt d'avis pour ce produit est réservé aux acheteurs. Veuillez vous connecter.")
            return redirect(product.get_absolute_url())

    form = ReviewForm(request.POST)
    if form.is_valid():
        review = form.save(commit=False)
        review.product = product
        # user = None pour les visiteurs anonymes (champ nullable dans le modèle)
        review.user = request.user if request.user.is_authenticated else None

        # Protection XSS
        review.client_name = strip_tags(review.client_name.strip())
        review.title = strip_tags(review.title.strip())
        review.comment = strip_tags(review.comment.strip())

        # Achat vérifié (False pour les anonymes)
        review.verified_purchase = is_buyer
        review.is_approved = False  # Nécessite validation de l'admin
        review.save()

        # Enregistrement de la notification d'administration
        try:
            title = f"Nouvel avis à modérer : {product.name}"
            user_info = request.user.username if request.user.is_authenticated else "Visiteur anonyme"
            message = (
                f"Produit : {product.name}\n"
                f"Client : {review.client_name} (User: {user_info})\n"
                f"Note : {review.rating}/5\n"
                f"Commentaire : {review.comment}"
            )
            AdminNotification.objects.create(
                title=title,
                message=message,
                notification_type='new_review'
            )

            # Envoi d'alertes par email / WhatsApp
            from .notifications import trigger_new_review_alerts
            trigger_new_review_alerts(review)
        except Exception as e:
            logger.error(f"Erreur lors de la notification de nouvel avis : {e}")

        messages.success(request, "Votre avis a été enregistré avec succès ! Il sera publié dès qu'il aura été validé par un administrateur.")
    else:
        for error_list in form.errors.values():
            for error in error_list:
                messages.error(request, error)

    return redirect(product.get_absolute_url())


def submit_general_review(request):
    """Traite un avis général affiché sur la page d'accueil.
    Accessible aux visiteurs connectés ET non connectés.
    """
    if request.method != 'POST':
        return redirect('core:home')

    form = ReviewForm(request.POST)
    if form.is_valid():
        review = form.save(commit=False)
        # user = None pour les visiteurs anonymes (champ nullable dans le modèle)
        review.user = request.user if request.user.is_authenticated else None
        review.client_name = strip_tags(review.client_name.strip())
        review.title = strip_tags(review.title.strip())
        review.comment = strip_tags(review.comment.strip())
        review.is_approved = False
        review.save()
        messages.success(request, "Votre avis a été enregistré. Il sera publié après validation.")
    else:
        for error_list in form.errors.values():
            for error in error_list:
                messages.error(request, error)
    return redirect('core:home')


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
