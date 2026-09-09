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
                "frame-ancestors 'none'",
                "base-uri 'self'",
                "form-action 'self'",
            ]
            response.headers.setdefault('Content-Security-Policy', '; '.join(csp_directives))

        return response
