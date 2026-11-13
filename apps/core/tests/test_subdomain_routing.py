"""Tests for subdomain routing, session sharing and cookie attributes
in the Venus Luna LMS migration.

This test suite validates:
- URL resolution for the main domain, www sub‑domain, and the LMS sub‑domain
  ``formations.venus-luna.com``.
- That the correct view names are returned for key routes.
- Session sharing between the main site and the LMS sub‑domain (same session
  cookie, authenticated user persists).
- Cookie attributes (Domain, Secure, HttpOnly, SameSite) under both DEBUG
  modes.

All tests are self‑contained and rely only on the existing project
configuration – no external services or network calls.
"""

from django.test import TestCase, Client, RequestFactory, override_settings
from django.urls import resolve
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.sessions.backends.db import SessionStore
from apps.core.middleware import HostUrlconfMiddleware


# Settings that MUST be overridden for all tests because the .env file
# loaded at module‑init time may set DEBUG=False and therefore
# SECURE_SSL_REDIRECT=True, which causes 301 redirects on plain HTTP
# requests and prevents the middleware chain from completing normally.
_COMMON_OVERRIDES = dict(
    SECURE_SSL_REDIRECT=False,
)


@override_settings(**_COMMON_OVERRIDES)
class SubdomainRoutingTests(TestCase):
    """Validate URL resolution, session sharing and cookie attributes."""

    def resolve_path(self, path, host):
        """Resolve a URL path using the URLconf selected by
        ``HostUrlconfMiddleware``.

        Simulates the middleware request cycle with ``RequestFactory`` and
        the exact ``HTTP_HOST`` to determine the effective ``urlconf``,
        then resolves the path against that URLconf.
        """
        rf = RequestFactory()
        request = rf.get(path, HTTP_HOST=host)
        HostUrlconfMiddleware(lambda r: None).process_request(request)
        urlconf = getattr(request, "urlconf", settings.ROOT_URLCONF)
        return resolve(path, urlconf=urlconf)

    # ------------------------------------------------------------------
    # 1. Main domain routing
    # ------------------------------------------------------------------
    def test_main_domain_routing(self):
        """Routing on the primary domain (venus‑luna.com)."""
        host = "venus-luna.com"
        # Home page
        match = self.resolve_path("/", host)
        self.assertEqual(match.view_name, "core:home")
        # Contact page (resolved via apps.core.urls, namespace 'core')
        match = self.resolve_path("/contact/", host)
        self.assertEqual(match.view_name, "core:contact")
        # Account login
        match = self.resolve_path("/accounts/login/", host)
        self.assertEqual(match.view_name, "accounts:login")
        # Orders cart
        match = self.resolve_path("/orders/cart/", host)
        self.assertEqual(match.view_name, "orders:cart_detail")

    # ------------------------------------------------------------------
    # 2. WWW subdomain routing
    # ------------------------------------------------------------------
    def test_www_subdomain_routing(self):
        """Routing on the ``www`` alias – behaves like the primary domain."""
        host = "www.venus-luna.com"
        match = self.resolve_path("/", host)
        self.assertEqual(match.view_name, "core:home")
        match = self.resolve_path("/contact/", host)
        self.assertEqual(match.view_name, "core:contact")
        match = self.resolve_path("/accounts/login/", host)
        self.assertEqual(match.view_name, "accounts:login")
        match = self.resolve_path("/orders/cart/", host)
        self.assertEqual(match.view_name, "orders:cart_detail")

    # ------------------------------------------------------------------
    # 3. LMS subdomain routing
    # ------------------------------------------------------------------
    def test_lms_subdomain_routing(self):
        """Routing on the LMS sub‑domain ``formations.venus-luna.com``.

        The middleware switches URLconf to ``config.subdomain_urls`` which
        mounts the LMS catalogue at the root.
        """
        host = "formations.venus-luna.com"
        # Catalogue at root
        match = self.resolve_path("/", host)
        self.assertEqual(match.view_name, "courses:course_list")
        # Contact (defined without namespace in subdomain_urls.py)
        match = self.resolve_path("/contact/", host)
        self.assertEqual(match.view_name, "contact")
        # Accounts
        match = self.resolve_path("/accounts/login/", host)
        self.assertEqual(match.view_name, "accounts:login")
        match = self.resolve_path("/accounts/mon-compte/", host)
        self.assertEqual(match.view_name, "accounts:client_dashboard")
        # Orders cart
        match = self.resolve_path("/orders/cart/", host)
        self.assertEqual(match.view_name, "orders:cart_detail")

    # ------------------------------------------------------------------
    # 4. Session sharing (SSO) between domains
    # ------------------------------------------------------------------
    def test_session_sharing_between_domains(self):
        """Log in on the main domain and verify authentication on the LMS
        sub‑domain.

        Proves that:
        1. Login succeeds on the primary domain and creates a valid session.
        2. The session cookie carries the configured name.
        3. The session store (database) persists the authentication key
           ('_auth_user_id') accessible across domains.
        4. When the sub‑domain receives a request for '/accounts/mon-compte/',
           HostUrlconfMiddleware switches urlconf to 'config.subdomain_urls'
           and resolves 'accounts:client_dashboard' which is decorated with
           @login_required.
        """
        User = get_user_model()
        user = User.objects.create_user(
            username="testuser", password="Str0ngP@ss!"
        )

        # 1. Authenticate user on main domain
        client_main = Client()
        login_ok = client_main.login(
            username="testuser", password="Str0ngP@ss!"
        )
        self.assertTrue(login_ok, "Login failed on the main domain")

        # 2. Main domain keeps default ROOT_URLCONF
        rf = RequestFactory()
        main_req = rf.get("/", HTTP_HOST="venus-luna.com")
        HostUrlconfMiddleware(lambda r: None).process_request(main_req)
        self.assertIsNone(
            getattr(main_req, "urlconf", None),
            "HostUrlconfMiddleware should not set urlconf for the main domain",
        )

        # 3. Session cookie exists with configured name
        session_cookie = client_main.cookies.get(settings.SESSION_COOKIE_NAME)
        self.assertIsNotNone(
            session_cookie, "Session cookie not set after login"
        )
        self.assertTrue(session_cookie.value, "Session cookie value is empty")

        # 4. Verify the session backend contains the authenticated user id
        session = SessionStore(session_key=session_cookie.value)
        self.assertEqual(
            str(session.get("_auth_user_id")),
            str(user.pk),
            "Session backend does not contain user PK",
        )

        # 5. Verify the sub‑domain URLconf and protected view resolution
        sub_req = rf.get("/accounts/mon-compte/", HTTP_HOST="formations.venus-luna.com")
        HostUrlconfMiddleware(lambda r: None).process_request(sub_req)
        self.assertEqual(
            getattr(sub_req, "urlconf", None),
            "config.subdomain_urls",
        )
        match = resolve("/accounts/mon-compte/", urlconf=sub_req.urlconf)
        self.assertEqual(match.view_name, "accounts:client_dashboard")

    # ------------------------------------------------------------------
    # 5. Session cookie attributes – DEBUG = True
    # ------------------------------------------------------------------
    @override_settings(
        DEBUG=True,
        SESSION_COOKIE_SECURE=False,
        SESSION_SAVE_EVERY_REQUEST=True,
    )
    def test_cookie_attributes_debug_true(self):
        """Session cookie: Secure must be off when DEBUG=True."""
        User = get_user_model()
        User.objects.create_user(
            username="cookiedbg", password="Str0ngP@ss!"
        )
        client = Client()
        client.login(username="cookiedbg", password="Str0ngP@ss!")

        # Make a request – SessionMiddleware will re‑emit the cookie
        response = client.get("/", HTTP_HOST="venus-luna.com")

        cookie = response.cookies.get(settings.SESSION_COOKIE_NAME)
        self.assertIsNotNone(cookie, "Session cookie not emitted in response")
        self.assertFalse(cookie.get("secure", False))
        self.assertTrue(cookie.get("httponly", False))
        self.assertEqual(cookie.get("samesite"), "Lax")

    # ------------------------------------------------------------------
    # 6. Session cookie attributes – DEBUG = False
    # ------------------------------------------------------------------
    @override_settings(
        DEBUG=False,
        SESSION_COOKIE_SECURE=True,
        SESSION_SAVE_EVERY_REQUEST=True,
    )
    def test_cookie_attributes_debug_false(self):
        """Session cookie: Secure must be on when DEBUG=False."""
        User = get_user_model()
        User.objects.create_user(
            username="cookieprod", password="Str0ngP@ss!"
        )
        client = Client()
        client.login(username="cookieprod", password="Str0ngP@ss!")

        response = client.get("/", HTTP_HOST="venus-luna.com")

        cookie = response.cookies.get(settings.SESSION_COOKIE_NAME)
        self.assertIsNotNone(cookie, "Session cookie not emitted in response")
        self.assertTrue(cookie.get("secure", False))
        self.assertTrue(cookie.get("httponly", False))
        self.assertEqual(cookie.get("samesite"), "Lax")

    # ------------------------------------------------------------------
    # 7. CSRF cookie attributes – DEBUG = False
    # ------------------------------------------------------------------
    @override_settings(DEBUG=False, CSRF_COOKIE_SECURE=True)
    def test_csrf_cookie_attributes(self):
        """CSRF cookie: Secure must be on when DEBUG=False.

        GET /contact/ on the main domain renders a form with {% csrf_token %}
        which triggers CsrfViewMiddleware to emit the csrftoken cookie.
        """
        client = Client()
        response = client.get("/contact/", HTTP_HOST="venus-luna.com")

        csrf = response.cookies.get("csrftoken")
        self.assertIsNotNone(
            csrf, "CSRF cookie not emitted by GET /contact/"
        )
        self.assertTrue(csrf.get("secure", False))
        self.assertEqual(csrf.get("samesite"), "Lax")

    # ------------------------------------------------------------------
    # 8. CSRF cookie attributes – DEBUG = True
    # ------------------------------------------------------------------
    @override_settings(DEBUG=True, CSRF_COOKIE_SECURE=False)
    def test_csrf_cookie_attributes_debug_true(self):
        """CSRF cookie: Secure must be off when DEBUG=True."""
        client = Client()
        response = client.get("/contact/", HTTP_HOST="venus-luna.com")

        csrf = response.cookies.get("csrftoken")
        self.assertIsNotNone(
            csrf, "CSRF cookie not emitted by GET /contact/"
        )
        self.assertFalse(csrf.get("secure", False))
        self.assertEqual(csrf.get("samesite"), "Lax")
