import logging
from django.shortcuts import render, redirect
from django.urls import reverse_lazy
from django.conf import settings
from django.contrib.auth import authenticate, login, logout, views as auth_views
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib import messages
from django.contrib.auth.models import User
from django.db.models import Sum, Count
from django.utils import timezone
from django.db.models.functions import TruncDay
from datetime import timedelta

logger = logging.getLogger(__name__)

# Imports de tes modèles
from apps.orders.models import Order, OrderItem 
from .forms import UserProfileForm, RegisterForm, EmailOrUsernameAuthForm


# --- RÉINITIALISATION DU MOT DE PASSE SÉCURISÉE ---

class CustomPasswordResetView(auth_views.PasswordResetView):
    """
    Vue de réinitialisation de mot de passe sécurisée et résiliente.
    - Évite l'erreur 500 en cas d'erreur SMTP / réseau
    - Force un domaine et protocole propres
    - Journalise l'erreur exacte pour l'administrateur
    - Protection contre l'énumération des utilisateurs
    """
    template_name = 'accounts/password_reset_form.html'
    email_template_name = 'emails/password_reset_email.txt'
    html_email_template_name = 'emails/password_reset_email.html'
    subject_template_name = 'emails/password_reset_subject.txt'
    success_url = reverse_lazy('accounts:password_reset_done')

    def form_valid(self, form):
        site_domain = getattr(settings, 'SITE_DOMAIN', 'venus-luna.com')
        protocol = 'https' if not getattr(settings, 'DEBUG', False) else 'http'
        opts = {
            'use_https': (protocol == 'https'),
            'token_generator': self.token_generator,
            'from_email': getattr(settings, 'DEFAULT_FROM_EMAIL', None),
            'email_template_name': self.email_template_name,
            'subject_template_name': self.subject_template_name,
            'request': self.request,
            'html_email_template_name': self.html_email_template_name,
            'extra_email_context': {
                'domain': site_domain,
                'site_name': 'Venus-Luna',
                'protocol': protocol,
            },
            'domain_override': site_domain,
        }
        try:
            form.save(**opts)
        except Exception as e:
            logger.error(f"[PASSWORD_RESET] Erreur lors de l'envoi de l'e-mail de réinitialisation : {e}", exc_info=True)
        return redirect(self.get_success_url())

# --- DASHBOARD ADMIN ---
@user_passes_test(lambda u: u.is_staff)
def admin_dashboard(request):
    total_orders = Order.objects.count()
    total_revenue = Order.objects.filter(status='delivered').aggregate(Sum('total'))['total__sum'] or 0
    total_customers = User.objects.filter(is_staff=False).count()
    pending_orders = Order.objects.filter(status='pending').count()
    
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

    category_data = (
        OrderItem.objects.filter(order__status='delivered')
        .values('product__category__name')
        .annotate(count=Count('id'))
        .order_by('-count')
    )
    pie_labels = [item['product__category__name'] or "Sans catégorie" for item in category_data]
    pie_values = [item['count'] for item in category_data]

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

# --- GESTION DES COMPTES ---

def register(request):
    if request.user.is_authenticated:
        return redirect('accounts:client_dashboard')
    if request.method == 'POST':
        form = RegisterForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            messages.success(request, f"Bienvenue {user.username} ! Votre compte a été créé.")
            return redirect('accounts:client_dashboard')
        messages.error(request, "Erreur lors de l'inscription. Veuillez corriger les champs.")
    else:
        form = RegisterForm()
    return render(request, 'accounts/register.html', {'form': form})

def login_view(request):
    if request.user.is_authenticated:
        return redirect('accounts:client_dashboard')
    if request.method == 'POST':
        form = EmailOrUsernameAuthForm(request, data=request.POST)
        if form.is_valid():
            user = form.get_user()
            login(request, user)
            next_url = request.GET.get('next')
            messages.success(request, f"Ravi de vous revoir, {user.username} !")
            return redirect(next_url or 'accounts:client_dashboard')
        messages.error(request, "Identifiants incorrects. Vérifiez votre nom d'utilisateur, e-mail ou mot de passe.")
    else:
        form = EmailOrUsernameAuthForm(request)
    return render(request, 'accounts/login.html', {'form': form})

def logout_view(request):
    logout(request)
    messages.info(request, "Vous avez été déconnecté.")
    return redirect('accounts:login')

@login_required
def client_dashboard(request):
    # C'est cette vue qui gère ta page principale "mon-compte"
    orders = Order.objects.filter(user=request.user).order_by('-created_at')
    return render(request, 'accounts/dashboard.html', {'orders': orders})

@login_required
def edit_profile(request):
    if request.method == 'POST':
        form = UserProfileForm(request.POST, instance=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, "Profil mis à jour avec succès.")
            return redirect('accounts:client_dashboard')
    else:
        form = UserProfileForm(instance=request.user)
    return render(request, 'accounts/edit_profile.html', {'form': form})