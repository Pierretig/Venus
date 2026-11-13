"""
Middleware de sécurité pour Venus Luna.
- En-têtes Permissions-Policy
- En-têtes Content-Security-Policy (CSP) adaptés aux services autorisés
"""

from django.conf import settings


class SecurityHeadersMiddleware:
    """
    Injecte les en-têtes Permissions-Policy et Content-Security-Policy.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)

        # 1. Permissions-Policy : interdiction des API matérielles non utilisées
        response.headers.setdefault(
            'Permissions-Policy',
            'camera=(), microphone=(), geolocation=(), payment=()'
        )

        # 2. Content-Security-Policy (uniquement en production / not DEBUG)
        if not getattr(settings, 'DEBUG', False):
            csp_directives = [
                "default-src 'self'",
                "img-src 'self' data: https://res.cloudinary.com https://*.cloudinary.com",
                "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://cdnjs.cloudflare.com",
                "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://fonts.googleapis.com https://cdnjs.cloudflare.com",
                "font-src 'self' data: https://fonts.gstatic.com https://cdnjs.cloudflare.com",
                "connect-src 'self' https://api.semoa-payments.ovh https://res.cloudinary.com",
                "media-src 'self' https://res.cloudinary.com https://*.cloudinary.com blob: data:",
                "frame-src 'self' https://www.youtube.com https://www.youtube-nocookie.com https://player.vimeo.com https://*.cloudinary.com",
                "frame-ancestors 'none'",
                "base-uri 'self'",
                "form-action 'self'",
            ]
            response.headers.setdefault('Content-Security-Policy', '; '.join(csp_directives))

        return response

# ---------------------------------------------------------------------------
# HostUrlconfMiddleware – moved here from apps/core/middleware/host_urlconf_middleware.py
# ---------------------------------------------------------------------------

"""Middleware to switch URLconf based on hostname.

The LMS is served from the sub‑domain ``formations.venus‑luna.com``. For any
request whose host (case‑insensitive, without port) matches that value we set
``request.urlconf`` to ``config.subdomain_urls`` so that Django resolves the
LMS‑specific routes. All other hosts keep the default ``ROOT_URLCONF``.
"""

from django.utils.deprecation import MiddlewareMixin


class HostUrlconfMiddleware(MiddlewareMixin):
    """Select the URL configuration according to the request host.

    * ``formations.venus-luna.com`` → ``config.subdomain_urls``
    * any other hostname → unchanged (uses ``ROOT_URLCONF``)
    """

    LMS_HOST = "formations.venus-luna.com"  # canonical host for the LMS

    def process_request(self, request):
        # ``request.get_host()`` returns ``host[:port]`` with the original case.
        host = request.get_host().split(":")[0].lower()
        if host == self.LMS_HOST.lower():
            request.urlconf = "config.subdomain_urls"
        # else: leave request.urlconf untouched
