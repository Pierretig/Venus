"""
Middleware et décorateur de Rate Limiting applicatif pour Venus Luna.
- Fonctionne sur le cache configuré dans Django (LocMemCache, DatabaseCache ou Redis).
- Ne nécessite pas de serveur Redis dédié.
- Empêche les attaques par force brute (connexion, réinitialisation de mot de passe, checkout).
"""

import time
import functools
import logging
from django.core.cache import cache
from django.http import HttpResponse
from django.contrib import messages
from django.shortcuts import redirect

logger = logging.getLogger('django.security')


def get_client_ip(request):
    """Extrait l'adresse IP client avec gestion du proxy inverse."""
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        return x_forwarded_for.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR', '127.0.0.1')


def ratelimit(rate='5/m', key='ip', block=True, redirect_url=None, error_message=None):
    """
    Décorateur de limitation de requêtes.
    - rate: '5/m' (5 par minute), '10/h' (10 par heure), '3/d' (3 par jour)
    - key: 'ip', 'post:email', ou callable(request)
    - block: Si True, bloque l'accès en cas de dépassement
    - redirect_url: URL vers laquelle rediriger en cas de blocage (au lieu d'un 429)
    - error_message: Message affiché à l'utilisateur
    """
    count_str, period_str = rate.split('/')
    max_requests = int(count_str)

    periods = {
        's': 1,
        'm': 60,
        'h': 3600,
        'd': 86400,
    }
    timeout = periods.get(period_str, 60)

    def decorator(view_func):
        @functools.wraps(view_func)
        def _wrapped_view(request, *args, **kwargs):
            # En méthode GET sur les formulaires d'inscription/connexion, on n'applique pas le rate limit
            # sauf si la vue est uniquement POST
            if request.method not in ('POST', 'PUT', 'DELETE') and key != 'all':
                return view_func(request, *args, **kwargs)

            # Résolution de la clé
            if key == 'ip':
                ident = get_client_ip(request)
            elif key == 'post:email':
                ident = f"{get_client_ip(request)}:{request.POST.get('email', '').strip().lower()}"
            elif callable(key):
                ident = key(request)
            else:
                ident = get_client_ip(request)

            view_name = f"{view_func.__module__}.{view_func.__name__}"
            cache_key = f"ratelimit:{view_name}:{ident}"

            current_requests = cache.get(cache_key, 0)
            if current_requests >= max_requests:
                logger.warning(
                    f"Rate limit dépassé pour {ident} sur {view_name} ({current_requests}/{max_requests} par {timeout}s)"
                )
                if block:
                    msg = error_message or "Trop de requêtes. Veuillez patienter avant de réessayer."
                    if redirect_url:
                        messages.error(request, msg)
                        return redirect(redirect_url)
                    return HttpResponse(f"Trop de requêtes. Veuillez patienter avant de réessayer. ({msg})", status=429)

            # Incrémentation
            try:
                if current_requests == 0:
                    cache.set(cache_key, 1, timeout=timeout)
                else:
                    cache.incr(cache_key)
            except Exception as e:
                # Si le cache rencontre une erreur, ne pas bloquer l'utilisateur légitime
                logger.error(f"Erreur de cache lors du rate limiting : {e}")

            return view_func(request, *args, **kwargs)

        return _wrapped_view

    return decorator
