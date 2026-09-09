import json
import jwt
from decimal import Decimal
from django.test import TestCase, Client, override_settings
from django.contrib.auth.models import User
from django.urls import reverse
from apps.orders.models import Order, ShippingAddress


class OrderSecurityTests(TestCase):
    def setUp(self):
        self.client = Client()
        # Utilisateur normal A
        self.user_a = User.objects.create_user(
            username='user_a', email='user_a@test.com', password='password123A!'
        )
        # Utilisateur normal B
        self.user_b = User.objects.create_user(
            username='user_b', email='user_b@test.com', password='password123B!'
        )
        # Administrateur (staff)
        self.staff_user = User.objects.create_user(
            username='staff_user', email='staff@test.com', password='passwordStaff1!', is_staff=True
        )

        # Commande appartenant à l'utilisateur A
        self.order_a = Order.objects.create(
            user=self.user_a,
            email=self.user_a.email,
            subtotal=Decimal('5000'),
            total=Decimal('5000'),
            status='pending',
            payment_status=False
        )
        ShippingAddress.objects.create(
            order=self.order_a,
            full_name='User A Full',
            phone='+22890000001',
            address='Quartier Test',
            city='Lomé'
        )

        # Commande invitée (sans compte)
        self.order_guest = Order.objects.create(
            user=None,
            email='guest@test.com',
            subtotal=Decimal('3000'),
            total=Decimal('3000'),
            status='pending',
            payment_status=False
        )
        ShippingAddress.objects.create(
            order=self.order_guest,
            full_name='Guest Client',
            phone='+22890000002',
            address='Quartier Invite',
            city='Lomé'
        )

    # -----------------------------------------------------------------------
    # 1. Contrôle d'accès au tableau de bord des commandes (orders:admin_dashboard)
    # -----------------------------------------------------------------------
    def test_dashboard_view_denied_for_anonymous(self):
        """Un visiteur non connecté est redirigé vers le login."""
        url = reverse('orders:admin_dashboard')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 302)
        self.assertIn('/accounts/login/', response.url)

    def test_dashboard_view_denied_for_normal_user(self):
        """Un client classique connecté ne peut PAS accéder au dashboard de gestion."""
        self.client.login(username='user_a', password='password123A!')
        url = reverse('orders:admin_dashboard')
        response = self.client.get(url)
        # user_passes_test redirige les non-staff vers le login
        self.assertEqual(response.status_code, 302)
        self.assertIn('/accounts/login/', response.url)

    def test_dashboard_view_allowed_for_staff(self):
        """Un administrateur (staff) accède correctement au dashboard."""
        self.client.login(username='staff_user', password='passwordStaff1!')
        url = reverse('orders:admin_dashboard')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

    # -----------------------------------------------------------------------
    # 2. Protection IDOR sur la confirmation de commande (order_confirm)
    # -----------------------------------------------------------------------
    def test_order_confirm_forbidden_for_other_user(self):
        """L'utilisateur B ne peut pas voir la confirmation de commande de l'utilisateur A."""
        self.client.login(username='user_b', password='password123B!')
        url = reverse('orders:order_confirm', kwargs={'order_id': self.order_a.id})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 404)

    def test_order_confirm_forbidden_for_anonymous_on_user_order(self):
        """Un visiteur non connecté est redirigé vers le login s'il tente d'accéder à la commande de A."""
        url = reverse('orders:order_confirm', kwargs={'order_id': self.order_a.id})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 302)

    def test_order_confirm_allowed_for_owner(self):
        """L'utilisateur A accède à sa propre confirmation de commande."""
        self.client.login(username='user_a', password='password123A!')
        url = reverse('orders:order_confirm', kwargs={'order_id': self.order_a.id})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

    def test_order_confirm_allowed_for_staff(self):
        """Le staff peut consulter la confirmation de commande."""
        self.client.login(username='staff_user', password='passwordStaff1!')
        url = reverse('orders:order_confirm', kwargs={'order_id': self.order_a.id})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

    def test_order_confirm_allowed_for_guest_with_matching_session(self):
        """Un invité avec le bon last_order_id en session accède à sa confirmation."""
        session = self.client.session
        session['last_order_id'] = self.order_guest.id
        session.save()

        url = reverse('orders:order_confirm', kwargs={'order_id': self.order_guest.id})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

    # -----------------------------------------------------------------------
    # 3. Protection IDOR sur le téléchargement de facture PDF (export_order_pdf)
    # -----------------------------------------------------------------------
    def test_export_pdf_forbidden_for_other_user(self):
        """L'utilisateur B ne peut pas télécharger la facture de l'utilisateur A."""
        self.client.login(username='user_b', password='password123B!')
        url = reverse('orders:export_pdf', kwargs={'order_id': self.order_a.id})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 404)

    def test_export_pdf_allowed_for_owner(self):
        """L'utilisateur A peut télécharger sa propre facture."""
        self.client.login(username='user_a', password='password123A!')
        url = reverse('orders:export_pdf', kwargs={'order_id': self.order_a.id})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/pdf')

    def test_export_pdf_allowed_for_staff(self):
        """Un administrateur peut télécharger n'importe quelle facture."""
        self.client.login(username='staff_user', password='passwordStaff1!')
        url = reverse('orders:export_pdf', kwargs={'order_id': self.order_a.id})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/pdf')

    # -----------------------------------------------------------------------
    # 4. Sécurité Webhook CashPay (Vérification de signature JWT)
    # -----------------------------------------------------------------------
    @override_settings(CASHPAY_SECRET_WEBHOOK='mon_secret_de_test_securise')
    def test_cashpay_webhook_rejects_forged_token(self):
        """Le webhook rejette (HTTP 401) un jeton dont la signature est falsifiée."""
        forged_token = jwt.encode(
            {'merchant_reference': str(self.order_a.id), 'state': 'Paid'},
            'mauvaise_cle_secrete',
            algorithm='HS256'
        )
        url = reverse('orders:cashpay_webhook')
        response = self.client.post(
            url,
            data=json.dumps({'token': forged_token}),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 401)
        # La commande ne doit PAS être marquée comme payée
        self.order_a.refresh_from_db()
        self.assertFalse(self.order_a.payment_status)

    @override_settings(CASHPAY_SECRET_WEBHOOK='mon_secret_de_test_securise')
    def test_cashpay_webhook_accepts_valid_signature(self):
        """Le webhook accepte un jeton valablement signé avec le secret configuré."""
        valid_token = jwt.encode(
            {'merchant_reference': str(self.order_a.id), 'state': 'Paid'},
            'mon_secret_de_test_securise',
            algorithm='HS256'
        )
        url = reverse('orders:cashpay_webhook')
        response = self.client.post(
            url,
            data=json.dumps({'token': valid_token}),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 200)
        self.order_a.refresh_from_db()
        self.assertTrue(self.order_a.payment_status)
        self.assertEqual(self.order_a.status, 'paid')
