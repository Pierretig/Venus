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
            {'merchant_reference': str(self.order_a.id), 'state': 'Paid', 'amount': 5000},
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

    @override_settings(CASHPAY_SECRET_WEBHOOK='')
    def test_cashpay_webhook_rejects_when_secret_not_configured(self):
        """Fail-Closed : le webhook rejette (HTTP 503) toute notification si le secret n'est pas configuré."""
        valid_token = jwt.encode(
            {'merchant_reference': str(self.order_a.id), 'state': 'Paid'},
            'cle_quelconque',
            algorithm='HS256'
        )
        url = reverse('orders:cashpay_webhook')
        response = self.client.post(
            url,
            data=json.dumps({'token': valid_token}),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 503)
        self.order_a.refresh_from_db()
        self.assertFalse(self.order_a.payment_status)

    @override_settings(CASHPAY_SECRET_WEBHOOK='mon_secret_de_test_securise')
    def test_cashpay_webhook_rejects_inconsistent_amount(self):
        """Le webhook rejette (HTTP 400) un jeton dont le montant payé est inférieur au total attendu."""
        underpaid_token = jwt.encode(
            {'merchant_reference': str(self.order_a.id), 'state': 'Paid', 'amount': 100},  # 100 au lieu de 5000
            'mon_secret_de_test_securise',
            algorithm='HS256'
        )
        url = reverse('orders:cashpay_webhook')
        response = self.client.post(
            url,
            data=json.dumps({'token': underpaid_token}),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 400)
        self.order_a.refresh_from_db()
        self.assertFalse(self.order_a.payment_status)


class CashpayReturnViewTests(TestCase):
    """
    Tests de la vue cashpay_return — vérification côté serveur du parcours post-paiement.

    TEST 1 : Paiement réussi → page de confirmation
    TEST 2 : Paiement refusé → pas de confirmation
    TEST 3 : Paiement annulé → pas de confirmation
    TEST 4 : Paiement en attente → page d'attente, pas de confirmation
    TEST 5 : Accès manuel frauduleux à l'URL success → impossible de falsifier
    TEST 6 : Callback reçu deux fois → idempotent (couvert par le webhook, testé ici côté vue)
    TEST 7 : Commande déjà payée → la vue affiche le succès, sans reprocessing
    TEST 8 : Montant incorrect → webhook rejette (déjà couvert par webhook tests)
    """
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username='test_user_return', email='return@test.com', password='ReturnPass123!'
        )
        self.order_pending = Order.objects.create(
            user=self.user, email=self.user.email,
            subtotal=Decimal('5000'), total=Decimal('5000'),
            status='pending', payment_status=False
        )
        ShippingAddress.objects.create(
            order=self.order_pending, full_name='Test Return',
            phone='+22890000099', address='Rue Test', city='Lomé'
        )
        self.order_paid = Order.objects.create(
            user=self.user, email=self.user.email,
            subtotal=Decimal('7500'), total=Decimal('7500'),
            status='paid', payment_status=True
        )
        ShippingAddress.objects.create(
            order=self.order_paid, full_name='Test Paid',
            phone='+22890000098', address='Rue Payee', city='Lomé'
        )
        self.order_cancelled = Order.objects.create(
            user=self.user, email=self.user.email,
            subtotal=Decimal('3000'), total=Decimal('3000'),
            status='cancelled', payment_status=False
        )
        ShippingAddress.objects.create(
            order=self.order_cancelled, full_name='Test Cancelled',
            phone='+22890000097', address='Rue Annulee', city='Lomé'
        )
        self.client.login(username='test_user_return', password='ReturnPass123!')

    # TEST 1 : Paiement réussi → page de confirmation (vérification BDD)
    def test_cashpay_return_shows_confirmed_page_when_paid(self):
        """Quand payment_status=True en BDD, cashpay_return affiche payment_confirmed.html."""
        url = reverse('orders:cashpay_return', kwargs={'order_id': self.order_paid.id})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'orders/payment_confirmed.html')
        self.assertContains(response, 'Paiement effectué avec succès')

    # TEST 1b : AJAX → JSON {paid: true}
    def test_cashpay_return_ajax_returns_json_when_paid(self):
        """En AJAX, cashpay_return retourne {paid: true} si le paiement est confirmé."""
        url = reverse('orders:cashpay_return', kwargs={'order_id': self.order_paid.id})
        response = self.client.get(url, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertTrue(data['paid'])

    # TEST 2/3 : Paiement refusé/annulé → page d'échec
    def test_cashpay_return_shows_failed_page_when_cancelled(self):
        """Quand status=cancelled, cashpay_return affiche payment_failed.html."""
        url = reverse('orders:cashpay_return', kwargs={'order_id': self.order_cancelled.id})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'orders/payment_failed.html')

    # TEST 4 : Paiement en attente → page d'attente (PAS de confirmation)
    def test_cashpay_return_shows_waiting_page_when_pending(self):
        """Quand payment_status=False et status=pending, cashpay_return affiche waiting_confirm.html."""
        url = reverse('orders:cashpay_return', kwargs={'order_id': self.order_pending.id})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'orders/waiting_confirm.html')
        # Ne doit PAS contenir le message de succès
        self.assertNotContains(response, 'Paiement effectué avec succès')

    # TEST 4b : AJAX en attente → JSON {paid: false}
    def test_cashpay_return_ajax_returns_not_paid_when_pending(self):
        """En AJAX sur commande pending, cashpay_return retourne {paid: false}."""
        url = reverse('orders:cashpay_return', kwargs={'order_id': self.order_pending.id})
        response = self.client.get(url, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertFalse(data['paid'])

    # TEST 5 : Accès manuel frauduleux → la vue vérifie la BDD, pas les params GET
    def test_cashpay_return_ignores_get_params_success(self):
        """Un attaquant passant ?status=success ne peut PAS déclencher une confirmation."""
        url = reverse('orders:cashpay_return', kwargs={'order_id': self.order_pending.id})
        # On passe le paramètre GET frauduleux : doit être IGNORÉ
        response = self.client.get(url + '?status=success&paid=true&state=Paid')
        self.assertEqual(response.status_code, 200)
        # La commande est toujours pending → waiting_confirm, PAS payment_confirmed
        self.assertTemplateUsed(response, 'orders/waiting_confirm.html')
        self.assertNotContains(response, 'Paiement effectué avec succès')
        # Vérification BDD : la commande N'EST PAS marquée comme payée
        self.order_pending.refresh_from_db()
        self.assertFalse(self.order_pending.payment_status)

    # TEST 5b : Accès d'un autre utilisateur → IDOR protection
    def test_cashpay_return_denies_other_user(self):
        """L'utilisateur B ne peut pas accéder à la page de retour de la commande de A."""
        other_user = User.objects.create_user(
            username='other_return', email='other_return@test.com', password='OtherPass123!'
        )
        self.client.logout()
        self.client.login(username='other_return', password='OtherPass123!')
        url = reverse('orders:cashpay_return', kwargs={'order_id': self.order_paid.id})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 404)

    # TEST 7 : Commande déjà payée → la vue affiche le succès (idempotent, pas de reprocessing)
    def test_cashpay_return_already_paid_shows_success_without_reprocessing(self):
        """Une commande déjà payée affiche la confirmation sans re-déclencher les traitements."""
        # Le signal post_save a déjà géré stock_updated=True lors du paiement initial
        # cashpay_return doit simplement afficher la page de confirmation
        url = reverse('orders:cashpay_return', kwargs={'order_id': self.order_paid.id})
        response1 = self.client.get(url)
        response2 = self.client.get(url)
        # Les deux requêtes doivent retourner la page de succès
        self.assertEqual(response1.status_code, 200)
        self.assertEqual(response2.status_code, 200)
        self.assertTemplateUsed(response1, 'orders/payment_confirmed.html')
        self.assertTemplateUsed(response2, 'orders/payment_confirmed.html')

    # TEST : URL 404 sur commande inexistante
    def test_cashpay_return_returns_404_for_nonexistent_order(self):
        """cashpay_return retourne 404 si l'order_id n'existe pas."""
        url = reverse('orders:cashpay_return', kwargs={'order_id': 99999})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 404)

    # TEST : Accès avec token signé (redirection cross-origin CashPay sans cookie session)
    def test_cashpay_return_with_valid_signed_token_allows_guest_access(self):
        """Un invité sans cookie de session peut accéder avec le token signé de redirect_url."""
        from django.core import signing
        # Créer un nouveau client vierge sans cookie
        fresh_client = Client()
        token = signing.dumps(self.order_paid.id, salt='cashpay-return')
        url = reverse('orders:cashpay_return', kwargs={'order_id': self.order_paid.id}) + f"?token={token}"
        response = fresh_client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'orders/payment_confirmed.html')

    # TEST : Rejet si token signé invalide pour une autre commande
    def test_cashpay_return_with_invalid_signed_token_denies_guest_access(self):
        """Un token falsifié ou pour un autre order_id est refusé."""
        from django.core import signing
        fresh_client = Client()
        invalid_token = signing.dumps(99999, salt='cashpay-return')
        url = reverse('orders:cashpay_return', kwargs={'order_id': self.order_paid.id}) + f"?token={invalid_token}"
        response = fresh_client.get(url)
        # Redirige vers login ou 404 car non autorisé
        self.assertIn(response.status_code, (302, 404))


class CashpayPaymentStatusEndpointTests(TestCase):
    """
    Tests exhaustifs du nouvel endpoint de polling :
    GET /orders/payment-status/<order_id>/?token=<signed_token>
    """
    def setUp(self):
        self.client = Client()
        self.order_paid = Order.objects.create(
            user=None,
            email="paid@example.com",
            subtotal=Decimal("5000"),
            total=Decimal("5000"),
            status="paid",
            payment_status=True,
            paygate_tx_id="SANDBOX-PAID-001"
        )
        self.order_pending = Order.objects.create(
            user=None,
            email="pending@example.com",
            subtotal=Decimal("4500"),
            total=Decimal("4500"),
            status="pending",
            payment_status=False,
            paygate_tx_id="SANDBOX-PENDING-002"
        )

    def _get_token(self, order_id):
        from django.core import signing
        return signing.dumps(order_id, salt='cashpay-return')

    def test_status_endpoint_returns_paid_when_already_paid(self):
        """Si la commande est déjà payée en BDD, retourne status=paid et redirect_url."""
        token = self._get_token(self.order_paid.id)
        url = reverse('orders:cashpay_payment_status', kwargs={'order_id': self.order_paid.id}) + f"?token={token}"
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data.get('status'), 'paid')
        self.assertTrue('redirect_url' in data)
        self.assertIn(f"/orders/retour/{self.order_paid.id}/", data['redirect_url'])

    def test_status_endpoint_returns_pending_when_pending_and_no_fallback(self):
        """Si en attente et API non interrogée ou toujours Pending, retourne status=pending."""
        from unittest.mock import patch
        token = self._get_token(self.order_pending.id)
        url = reverse('orders:cashpay_payment_status', kwargs={'order_id': self.order_pending.id}) + f"?token={token}"
        
        with patch('apps.orders.cashpay_service.CashPayService.get_order_status') as mock_status:
            mock_status.return_value = {'state': 'Pending'}
            response = self.client.get(url)
            self.assertEqual(response.status_code, 200)
            data = response.json()
            self.assertEqual(data.get('status'), 'pending')

    def test_status_endpoint_fallback_api_confirms_paid(self):
        """Quand l'API CashPay retourne 'Paid', la BDD est mise à jour et status=paid est renvoyé."""
        from unittest.mock import patch
        token = self._get_token(self.order_pending.id)
        url = reverse('orders:cashpay_payment_status', kwargs={'order_id': self.order_pending.id}) + f"?token={token}"
        
        with patch('apps.orders.cashpay_service.CashPayService.get_order_status') as mock_status:
            mock_status.return_value = {'state': 'Paid'}
            response = self.client.get(url)
            self.assertEqual(response.status_code, 200)
            data = response.json()
            self.assertEqual(data.get('status'), 'paid')
            self.assertTrue('redirect_url' in data)

        # Vérification BDD : commande marquée payée
        self.order_pending.refresh_from_db()
        self.assertTrue(self.order_pending.payment_status)
        self.assertEqual(self.order_pending.status, 'paid')

    def test_status_endpoint_fallback_api_detects_cancelled(self):
        """Quand l'API CashPay retourne 'Canceled', la commande est annulée et status=failed est renvoyé."""
        from unittest.mock import patch
        token = self._get_token(self.order_pending.id)
        url = reverse('orders:cashpay_payment_status', kwargs={'order_id': self.order_pending.id}) + f"?token={token}"
        
        with patch('apps.orders.cashpay_service.CashPayService.get_order_status') as mock_status:
            mock_status.return_value = {'state': 'Canceled'}
            response = self.client.get(url)
            self.assertEqual(response.status_code, 200)
            data = response.json()
            self.assertEqual(data.get('status'), 'failed')

        self.order_pending.refresh_from_db()
        self.assertEqual(self.order_pending.status, 'cancelled')

    def test_status_endpoint_fallback_api_detects_expired(self):
        """Quand l'API CashPay retourne 'Expired', status=expired est renvoyé."""
        from unittest.mock import patch
        token = self._get_token(self.order_pending.id)
        url = reverse('orders:cashpay_payment_status', kwargs={'order_id': self.order_pending.id}) + f"?token={token}"
        
        with patch('apps.orders.cashpay_service.CashPayService.get_order_status') as mock_status:
            mock_status.return_value = {'state': 'Expired'}
            response = self.client.get(url)
            self.assertEqual(response.status_code, 200)
            data = response.json()
            self.assertEqual(data.get('status'), 'expired')

    def test_status_endpoint_denies_access_without_token_or_session(self):
        """Accès interdit (403) sans session valide et sans token signé."""
        fresh_client = Client()
        url = reverse('orders:cashpay_payment_status', kwargs={'order_id': self.order_pending.id})
        response = fresh_client.get(url)
        self.assertEqual(response.status_code, 403)

    def test_status_endpoint_returns_404_for_nonexistent_order(self):
        """Retourne 404 pour un order_id inexistant."""
        url = reverse('orders:cashpay_payment_status', kwargs={'order_id': 99999})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 404)

    def test_status_endpoint_ignores_fraudulent_get_params(self):
        """Un paramètre ?status=paid passé dans l'URL ne déclenche PAS de confirmation sans preuve réelle."""
        from unittest.mock import patch
        token = self._get_token(self.order_pending.id)
        url = reverse('orders:cashpay_payment_status', kwargs={'order_id': self.order_pending.id}) + f"?token={token}&status=paid&paid=true"
        
        with patch('apps.orders.cashpay_service.CashPayService.get_order_status') as mock_status:
            mock_status.return_value = {'state': 'Pending'}
            response = self.client.get(url)
            self.assertEqual(response.status_code, 200)
            data = response.json()
            self.assertEqual(data.get('status'), 'pending')

        self.order_pending.refresh_from_db()
        self.assertFalse(self.order_pending.payment_status)
