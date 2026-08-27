# ...existing code...
from django.urls import path, reverse_lazy
from django.contrib.auth import views as auth_views
from . import views

app_name = 'accounts'

urlpatterns = [
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('register/', views.register, name='register'),
    path(
        'mot-de-passe/oublie/',
        views.CustomPasswordResetView.as_view(),
        name='password_reset',
    ),
    path(
        'mot-de-passe/email-envoye/',
        auth_views.PasswordResetDoneView.as_view(
            template_name='accounts/password_reset_done.html',
        ),
        name='password_reset_done',
    ),
    path(
        'mot-de-passe/reinitialiser/<uidb64>/<token>/',
        auth_views.PasswordResetConfirmView.as_view(
            template_name='accounts/password_reset_confirm.html',
            success_url=reverse_lazy('accounts:password_reset_complete'),
        ),
        name='password_reset_confirm',
    ),
    path(
        'mot-de-passe/reinitialisation-terminee/',
        auth_views.PasswordResetCompleteView.as_view(
            template_name='accounts/password_reset_complete.html',
        ),
        name='password_reset_complete',
    ),
    
    path('mon-compte/', views.client_dashboard, name='client_dashboard'),
    path('mon-compte/modifier/', views.edit_profile, name='profile_edit'),
    # Espace Gestion Boutique (Admin)
    path('gestion-boutique/', views.admin_dashboard, name='admin_dashboard'),

]
# ...existing code...