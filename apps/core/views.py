import logging
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.conf import settings
from django.apps import apps
from django.http import Http404

# Import des utilitaires watermark
from .utils.watermark import get_clean_url, get_watermarked_url

# Import des modèles de l'application Core
from .models import Banner, SiteSettings, SocialLink

# Import des modèles des autres applications
from apps.products.models import Product, Category 
from apps.products.forms import ReviewForm
from apps.blog.models import Post
from apps.contact.forms import ContactForm

logger = logging.getLogger(__name__)


def cgv_view(request):
    return render(request, 'pages/cgv.html') # Assure-toi que ce template existe


def serve_image(request, app_label, model_name, pk, field_name):
    """
    Vue proxy qui sert les images Cloudinary avec ou sans watermark
    selon la provenance de la requête.

    - Affichage interne (depuis une page du site)  → image PROPRE
    - Accès direct, hotlink, outils CLI (curl/wget) → image WATERMARKÉE

    L'URL utilise le modèle Django et la PK ; le public_id Cloudinary
    n'est JAMAIS exposé dans le HTML.
    """
    model = apps.get_model(app_label, model_name)
    instance = get_object_or_404(model, pk=pk)

    field = getattr(instance, field_name, None)
    if not field:
        # Fallback image au lieu de planter (sinon 500 sur la boutique)
        fallback = 'img/aze1.png'
        return redirect(fallback if fallback.startswith('/') else f'/{fallback}')

    public_id = str(field)
    if not public_id:
        fallback = 'img/aze1.png'
        return redirect(fallback if fallback.startswith('/') else f'/{fallback}')


    referer = request.META.get('HTTP_REFERER', '')
    user_agent = request.META.get('HTTP_USER_AGENT', '').lower()
    site_domain = getattr(settings, 'SITE_DOMAIN', '')

    # Détection des outils CLI / scrapers
    cli_tools = ['curl', 'wget', 'python-requests', 'scrapy', 'httpx', 'aiohttp', 'libwww']
    is_cli = any(tool in user_agent for tool in cli_tools)

    # Détection des crawlers sociaux / SEO (ils méritent des images propres)
    social_crawlers = [
        'facebookexternalhit', 'twitterbot', 'linkedinbot', 'whatsapp',
        'slackbot', 'discordbot', 'googlebot', 'bingbot', 'applebot',
    ]
    is_crawler = any(bot in user_agent for bot in social_crawlers)

    # Accès direct = pas de referer OU domaine externe
    is_direct = not referer or (site_domain and site_domain not in referer)

    if (is_direct or is_cli) and not is_crawler:
        logger.info(
            "Watermark servi pour %s.%s:%s — Referer: %s, UA: %s",
            app_label, model_name, pk, referer, user_agent
        )
        url = get_watermarked_url(public_id)
    else:
        url = get_clean_url(public_id)

    return redirect(url)


def home(request):
    """
    Vue unique de la page d'accueil.
    Regroupe les bannières, les produits, les catégories et les articles de blog.
    """
    # 1. Récupération des bannières actives
    banners = Banner.objects.filter(is_active=True).order_by('order', '-created_at')
    
    # 2. Récupération des paramètres du site et liens sociaux
    site_settings = SiteSettings.get_solo()
    social_links = SocialLink.objects.all()
    
    # 3. Récupération des 6 derniers produits
    products = Product.objects.all().order_by('-created_at')[:6]
    
    # 4. Récupération de toutes les catégories pour le menu ou la grille
    categories = Category.objects.all()
    
    # 5. Récupération des 3 derniers articles de blog PUBLIÉS
    posts = Post.objects.filter(published=True).order_by('-created_at')[:3]

    # 6. Avis dynamiques pour la section "Ils ont trouvé la paix"
    testimonials = []
    static_testimonials = []
    reviews_section_enabled = True

    if site_settings:
        reviews_section_enabled = site_settings.reviews_homepage_enabled
        max_reviews = site_settings.reviews_homepage_limit or 6
        mode = site_settings.reviews_homepage_mode or 'mix'
    else:
        max_reviews = 6
        mode = 'mix'

    if reviews_section_enabled:
        # Import local pour éviter les importations circulaires
        from apps.products.models import Review

        # Construction du queryset selon le mode choisi
        base_qs = Review.objects.filter(is_approved=True).select_related('product', 'user__profile')

        if mode == 'recent':
            real_reviews = list(base_qs.order_by('-created_at')[:max_reviews])
        elif mode == 'best':
            real_reviews = list(base_qs.filter(rating__gte=4).order_by('-rating', '-created_at')[:max_reviews])
        elif mode == 'pinned':
            real_reviews = list(base_qs.filter(is_pinned=True).order_by('-created_at')[:max_reviews])
        else:  # 'mix' : d'abord les épinglés, ensuite les mieux notés/récents
            pinned = list(base_qs.filter(is_pinned=True).order_by('-created_at')[:max_reviews])
            remaining_slots = max_reviews - len(pinned)
            if remaining_slots > 0:
                pinned_ids = [r.id for r in pinned]
                others = list(
                    base_qs.exclude(id__in=pinned_ids)
                    .order_by('-rating', '-created_at')[:remaining_slots]
                )
            else:
                others = []
            real_reviews = pinned + others

        # Témoignages statiques de remplacement progressif
        DEFAULT_TESTIMONIALS = [
            {
                "client_name": "Ablavi M.",
                "comment": "Les pierres de Venus Luna ont totalement changé l'énergie de mon bureau. Je me sens beaucoup plus apaisée.",
                "rating": 5,
                "verified_purchase": False,
                "product": None,
            },
            {
                "client_name": "Koffi T.",
                "comment": "Service client exceptionnel et livraison très rapide à Adidoadin. Je recommande vivement !",
                "rating": 5,
                "verified_purchase": False,
                "product": None,
            },
            {
                "client_name": "Emefa S.",
                "comment": "Des articles spirituels de qualité qu'on ne trouve nulle part ailleurs au Togo.",
                "rating": 5,
                "verified_purchase": False,
                "product": None,
            },
            {
                "client_name": "Yawa D.",
                "comment": "Mes bougies sentent divinement bon. Un vrai rituel de bien-être à la maison.",
                "rating": 5,
                "verified_purchase": False,
                "product": None,
            },
            {
                "client_name": "Kossi A.",
                "comment": "L'encens Palo Santo a un parfum unique. Je suis fan de cette boutique depuis ma première commande.",
                "rating": 5,
                "verified_purchase": False,
                "product": None,
            },
            {
                "client_name": "Mawuli K.",
                "comment": "Commande reçue dans les délais, packaging soigné et produits de qualité supérieure. Merci !",
                "rating": 5,
                "verified_purchase": False,
                "product": None,
            },
        ]

        # Remplissage progressif : vrais avis en premier, statiques en complement
        slots_remaining = max_reviews - len(real_reviews)
        static_testimonials = DEFAULT_TESTIMONIALS[:slots_remaining] if slots_remaining > 0 else []
        testimonials = real_reviews
    
    # Construction du contexte unique
    context = {
        'banners': banners,
        'site_settings': site_settings,
        'social_links': social_links,
        'products': products,
        'categories': categories,
        'posts': posts,
        'testimonials': testimonials,
        'static_testimonials': static_testimonials,
        'reviews_section_enabled': reviews_section_enabled,
        'review_form': ReviewForm(initial={
            'client_name': (request.user.first_name or request.user.username)
            if request.user.is_authenticated else ''
        }),
    }
    
    return render(request, 'pages/home.html', context)

def about(request):
    """Page À Propos"""
    return render(request, 'pages/about.html')

def contact_view(request):
    """Gestion du formulaire de contact"""
    if request.method == 'POST':
        form = ContactForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Votre message a été transmis avec succès.")
            return redirect('core:contact')
    else:
        form = ContactForm()
    
    return render(request, 'pages/contact.html', {'form': form})

def confidentialite(request):
    """Page Politique de Confidentialité"""
    return render(request, 'pages/confidentialite.html')

def faq(request):
    """Page Foire Aux Questions"""
    return render(request, 'pages/faq.html')

def custom_404(request, exception):
    """Page d'erreur 404 personnalisée"""
    return render(request, 'pages/404.html', status=404)