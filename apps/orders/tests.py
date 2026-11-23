import json
import jwt
from decimal import Decimal
from django.test import TestCase, TransactionTestCase, Client, override_settings
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
            # Réponse GET /orders/{reference} (doc CashPay V3.1) : billed_amount = total, amount = reste dû.
            mock_status.return_value = {'state': 'Paid', 'billed_amount': 4500, 'amount': 0, 'currency': 'XOF'}
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


class CheckoutFormPhoneAndPrefillTests(TestCase):
    """
    Tests de la validation du téléphone togolais dans CheckoutForm et du
    préremplissage pour les utilisateurs connectés / invités.
    """

    def test_checkout_form_valid_phone_normalized(self):
        """CheckoutForm valide et normalise un numéro togolais avec séparateurs."""
        from apps.orders.forms import CheckoutForm
        form = CheckoutForm(data={
            'full_name': 'Afi Mensah',
            'email': 'afi@example.com',
            'phone': '+228 96.01.02.03',
            'address': 'Rue de la Paix',
            'city': 'Lomé',
            'country': 'Togo',
        })
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data['phone'], '22896010203')

    def test_checkout_form_invalid_phone_rejected(self):
        """CheckoutForm rejette un préfixe togolais non agréé."""
        from apps.orders.forms import CheckoutForm
        form = CheckoutForm(data={
            'full_name': 'Afi Mensah',
            'email': 'afi@example.com',
            'phone': '00000000',
            'address': 'Rue de la Paix',
            'city': 'Lomé',
            'country': 'Togo',
        })
        self.assertFalse(form.is_valid())
        self.assertIn('phone', form.errors)

    def test_checkout_initial_authenticated_with_profile(self):
        """_get_checkout_initial préremplit tous les champs pour un client connecté avec profil."""
        from apps.orders.views import _get_checkout_initial
        user = User.objects.create_user(
            username='user_prefill_full',
            email='full@example.com',
            first_name='Koffi',
            last_name='Mensah',
            password='Password123!'
        )
        profile = user.profile
        profile.phone = '22890010203'
        profile.address = 'Quartier Bè'
        profile.city = 'Lomé'
        profile.save()

        initial = _get_checkout_initial(user)
        self.assertEqual(initial['full_name'], 'Koffi Mensah')
        self.assertEqual(initial['email'], 'full@example.com')
        self.assertEqual(initial['phone'], '22890010203')
        self.assertEqual(initial['address'], 'Quartier Bè')
        self.assertEqual(initial['city'], 'Lomé')
        self.assertEqual(initial['country'], 'Togo')

    def test_checkout_initial_guest_empty(self):
        """_get_checkout_initial retourne un dictionnaire vide pour un invité anonyme."""
        from django.contrib.auth.models import AnonymousUser
        from apps.orders.views import _get_checkout_initial
        initial = _get_checkout_initial(AnonymousUser())
        self.assertEqual(initial, {})


@override_settings(SECURE_SSL_REDIRECT=False)
class CashPayAtomicPaymentTests(TransactionTestCase):
    """
    Tests de sécurité, atomicité et concurrence pour le cycle de paiement CashPay.
    Exécutés sous TransactionTestCase pour permettre de vraies transactions et
    des connexions distinctes multi-threads sur PostgreSQL.
    """
    reset_sequences = True

    def setUp(self):
        self.client = Client()
        from apps.products.models import Product
        from apps.courses.models import Course
        self.user = User.objects.create_user(
            username='client_atomic',
            email='client_atomic@example.com',
            password='TestPassword123!'
        )
        self.product_a = Product.objects.create(
            name='Produit Alpha Test',
            price=Decimal('5000'),
            stock=10,
        )
        self.product_b = Product.objects.create(
            name='Produit Beta Test',
            price=Decimal('3000'),
            stock=15,
        )
        self.course = Course.objects.create(
            title='Formation Énergétique Test',
            description='Formation complète en ligne',
        )
        # Versionnement : une formation n'est vendable qu'avec une révision publiée.
        from apps.courses.testing import publish_working_copy
        self.course_revision = publish_working_copy(self.course)

    def _create_order(self, products_with_qty=None, course=None):
        from apps.orders.models import OrderItem
        order = Order.objects.create(
            user=self.user,
            email=self.user.email,
            status='pending',
            payment_status=False,
            subtotal=Decimal('0'),
            total=Decimal('0'),
        )
        total = Decimal('0')
        if products_with_qty:
            for prod, qty in products_with_qty:
                OrderItem.objects.create(
                    order=order,
                    product=prod,
                    name=prod.name,
                    price=prod.price,
                    quantity=qty,
                )
                total += prod.price * qty

        if course:
            OrderItem.objects.create(
                order=order,
                course=course,
                name=course.title,
                price=Decimal('15000'),
                quantity=1,
            )
            total += Decimal('15000')

        order.subtotal = total
        order.total = total
        order.save(update_fields=['subtotal', 'total'])
        return order

    def test_01_first_valid_confirmation(self):
        """1. Première confirmation valide : transition vers paid, stock déduit, mouvement SALE créé."""
        from apps.orders.payment_processing import confirm_order_payment
        from apps.products.models import StockMovement
        order = self._create_order(products_with_qty=[(self.product_a, 2)])
        initial_stock = self.product_a.stock

        confirmed, updated_order, reason = confirm_order_payment(
            order_id=order.id,
            transaction_ref='CP_TX_001',
            amount_received=order.total,
        )

        self.assertTrue(confirmed)
        self.assertEqual(reason, 'confirmed')
        self.assertEqual(updated_order.status, 'paid')
        self.assertTrue(updated_order.payment_status)
        self.assertTrue(updated_order.stock_updated)
        self.assertEqual(updated_order.paygate_tx_id, 'CP_TX_001')

        self.product_a.refresh_from_db()
        self.assertEqual(self.product_a.stock, initial_stock - 2)

        movements = StockMovement.objects.filter(order=order)
        self.assertEqual(movements.count(), 1)
        self.assertEqual(movements.first().movement_type, StockMovement.MovementType.SALE)
        self.assertEqual(movements.first().quantity, -2)

    def test_02_second_identical_confirmation(self):
        """2. Deuxième confirmation identique : idempotence stricte, aucun double traitement."""
        from apps.orders.payment_processing import confirm_order_payment
        from apps.products.models import StockMovement
        order = self._create_order(products_with_qty=[(self.product_a, 2)])

        # 1ère confirmation
        c1, o1, r1 = confirm_order_payment(order.id, transaction_ref='CP_TX_002', amount_received=order.total)
        self.assertTrue(c1)
        self.product_a.refresh_from_db()
        stock_after_first = self.product_a.stock

        # 2ème confirmation identique
        c2, o2, r2 = confirm_order_payment(order.id, transaction_ref='CP_TX_002', amount_received=order.total)
        self.assertFalse(c2)
        self.assertEqual(r2, 'already_paid')

        self.product_a.refresh_from_db()
        self.assertEqual(self.product_a.stock, stock_after_first)
        self.assertEqual(StockMovement.objects.filter(order=order).count(), 1)

    @override_settings(CASHPAY_SECRET_WEBHOOK='test_secret_key_123456789_cashpay_secret_key_32bytes', SECURE_SSL_REDIRECT=False)
    def test_03_repeated_webhook(self):
        """3. Webhook répété : les 2 appels HTTP renvoient 200, mais le stock n'est déduit qu'une fois."""
        from apps.products.models import StockMovement
        order = self._create_order(products_with_qty=[(self.product_a, 3)])
        initial_stock = self.product_a.stock

        token_payload = {
            'order_reference': 'CP_REF_WEBHOOK',
            'merchant_reference': str(order.id),
            'state': 'Paid',
            'amount': str(order.total),
        }
        token = jwt.encode(token_payload, 'test_secret_key_123456789_cashpay_secret_key_32bytes', algorithm='HS256')
        url = reverse('orders:cashpay_webhook')

        # Premier appel webhook
        r1 = self.client.post(url, data=json.dumps({'token': token}), content_type='application/json')
        self.assertEqual(r1.status_code, 200)

        order.refresh_from_db()
        self.assertEqual(order.status, 'paid')
        self.product_a.refresh_from_db()
        self.assertEqual(self.product_a.stock, initial_stock - 3)
        self.assertEqual(StockMovement.objects.filter(order=order).count(), 1)

        # Deuxième appel webhook identique
        r2 = self.client.post(url, data=json.dumps({'token': token}), content_type='application/json')
        self.assertEqual(r2.status_code, 200)

        self.product_a.refresh_from_db()
        self.assertEqual(self.product_a.stock, initial_stock - 3)
        self.assertEqual(StockMovement.objects.filter(order=order).count(), 1)

    def test_04_polling_after_webhook_confirmation(self):
        """4. Polling après confirmation par webhook : renvoie 'status': 'paid' sans réexécuter."""
        from apps.orders.payment_processing import confirm_order_payment
        from apps.products.models import StockMovement
        order = self._create_order(products_with_qty=[(self.product_a, 1)])
        confirm_order_payment(order.id, transaction_ref='CP_WEBHOOK_DONE')

        self.client.login(username='client_atomic', password='TestPassword123!')
        url = reverse('orders:cashpay_payment_status', kwargs={'order_id': order.id})
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data.get('status'), 'paid')
        self.assertIn('redirect_url', data)

        self.assertEqual(StockMovement.objects.filter(order=order).count(), 1)

    def test_05_return_after_webhook_confirmation(self):
        """5. Vue de retour après confirmation webhook : affiche le statut payé sans double traitement."""
        from apps.orders.payment_processing import confirm_order_payment
        from apps.products.models import StockMovement
        from django.core import signing
        order = self._create_order(products_with_qty=[(self.product_a, 1)])
        confirm_order_payment(order.id, transaction_ref='CP_WEBHOOK_FIRST')

        self.client.login(username='client_atomic', password='TestPassword123!')
        token = signing.dumps(order.id, salt='cashpay-return')
        url = reverse('orders:cashpay_return', kwargs={'order_id': order.id}) + f"?token={token}"
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(StockMovement.objects.filter(order=order).count(), 1)

    def test_06_concurrent_confirmations(self):
        """6. Deux confirmations concurrentes (threads + connexions PostgreSQL distinctes)."""
        import threading
        from django.db import connections
        from apps.orders.payment_processing import confirm_order_payment
        from apps.products.models import StockMovement

        order = self._create_order(products_with_qty=[(self.product_a, 4)])
        initial_stock = self.product_a.stock
        order_id = order.id

        results = [None, None]

        def worker(index, tx_ref):
            connections.close_all()
            try:
                c, o, r = confirm_order_payment(order_id=order_id, transaction_ref=tx_ref)
                results[index] = (c, r)
            except Exception as e:
                results[index] = e
            finally:
                connections.close_all()

        t1 = threading.Thread(target=worker, args=(0, 'TX_CONCURRENT'))
        t2 = threading.Thread(target=worker, args=(1, 'TX_CONCURRENT'))

        t1.start()
        t2.start()
        t1.join()
        t2.join()

        confirmed_count = sum(1 for res in results if isinstance(res, tuple) and res[0] is True)
        already_paid_count = sum(1 for res in results if isinstance(res, tuple) and res[1] == 'already_paid')

        self.assertEqual(confirmed_count, 1, f"Résultats inattendus: {results}")
        self.assertEqual(already_paid_count, 1, f"Résultats inattendus: {results}")

        self.product_a.refresh_from_db()
        self.assertEqual(self.product_a.stock, initial_stock - 4)
        self.assertEqual(StockMovement.objects.filter(order=order).count(), 1)

    def test_07_single_stock_deduction(self):
        """7. Une seule déduction de stock sur plusieurs tentatives séquentielles."""
        from apps.orders.payment_processing import confirm_order_payment
        from apps.products.models import StockMovement
        order = self._create_order(products_with_qty=[(self.product_b, 5)])
        initial_stock = self.product_b.stock

        for i in range(3):
            confirm_order_payment(order.id, transaction_ref='TX_REP_SAME')

        self.product_b.refresh_from_db()
        self.assertEqual(self.product_b.stock, initial_stock - 5)
        self.assertEqual(StockMovement.objects.filter(order=order).count(), 1)

    def test_08_single_sale_movement_per_order_item(self):
        """8. Un seul mouvement SALE par ligne de commande traitée."""
        from apps.orders.payment_processing import confirm_order_payment
        from apps.products.models import StockMovement
        order = self._create_order(products_with_qty=[
            (self.product_a, 2),
            (self.product_b, 3),
        ])

        confirm_order_payment(order.id, transaction_ref='TX_MULTI_ITEMS')
        confirm_order_payment(order.id, transaction_ref='TX_MULTI_ITEMS')

        movements = StockMovement.objects.filter(order=order)
        self.assertEqual(movements.count(), 2)
        m_a = movements.filter(product=self.product_a).first()
        m_b = movements.filter(product=self.product_b).first()

        self.assertIsNotNone(m_a)
        self.assertIsNotNone(m_b)
        self.assertEqual(m_a.quantity, -2)
        self.assertEqual(m_b.quantity, -3)

    def test_09_rollback_on_stock_failure(self):
        """9. Rollback complet de la commande en cas de stock insuffisant."""
        from apps.orders.payment_processing import confirm_order_payment, InsufficientStockError
        from apps.products.models import Product, StockMovement
        product_low = Product.objects.create(name='Produit Rare Test', price=Decimal('1000'), stock=1)
        order = self._create_order(products_with_qty=[(product_low, 10)])

        with self.assertRaises(InsufficientStockError):
            confirm_order_payment(order.id, transaction_ref='TX_FAIL_STOCK')

        order.refresh_from_db()
        self.assertEqual(order.status, 'pending')
        self.assertFalse(order.payment_status)
        self.assertFalse(order.stock_updated)

        product_low.refresh_from_db()
        self.assertEqual(product_low.stock, 1)
        self.assertEqual(StockMovement.objects.filter(order=order).count(), 0)

    def test_10_course_enrollment_preservation(self):
        """10. Préservation et non-duplication des inscriptions aux formations numériques."""
        from apps.orders.payment_processing import confirm_order_payment
        from apps.courses.models import Enrollment

        order = self._create_order(course=self.course)

        c1, o1, r1 = confirm_order_payment(order.id, transaction_ref='TX_COURSE_1')
        self.assertTrue(c1)

        enrollments = Enrollment.objects.filter(user=self.user, course=self.course)
        self.assertEqual(enrollments.count(), 1)
        enrollment = enrollments.first()
        self.assertEqual(enrollment.status, Enrollment.Status.ACTIVE)
        self.assertEqual(enrollment.order, order)

        c2, o2, r2 = confirm_order_payment(order.id, transaction_ref='TX_COURSE_1')
        self.assertFalse(c2)

        self.assertEqual(Enrollment.objects.filter(user=self.user, course=self.course).count(), 1)

    def test_11_deterministic_lock_order_and_item_consolidation(self):
        """11. Verrouillage déterministe (par product_id croissant) et consolidation multi-lignes."""
        from apps.orders.payment_processing import confirm_order_payment
        from apps.orders.models import OrderItem
        from apps.products.models import StockMovement

        # Créer une commande avec Product B (id > A) puis Product A (id < B),
        # et une seconde ligne pour Product A (consolidation de quantité)
        order = Order.objects.create(
            user=self.user,
            email=self.user.email,
            status='pending',
            payment_status=False,
            subtotal=Decimal('11000'),
            total=Decimal('11000'),
        )
        # Ligne 1 : Product B (quantité 2)
        OrderItem.objects.create(order=order, product=self.product_b, name=self.product_b.name, price=self.product_b.price, quantity=2)
        # Ligne 2 : Product A (quantité 1)
        OrderItem.objects.create(order=order, product=self.product_a, name=self.product_a.name, price=self.product_a.price, quantity=1)
        # Ligne 3 : Product A encore (quantité 2) -> total requis pour A = 3
        OrderItem.objects.create(order=order, product=self.product_a, name=self.product_a.name, price=self.product_a.price, quantity=2)

        initial_a = self.product_a.stock
        initial_b = self.product_b.stock

        confirmed, updated_order, reason = confirm_order_payment(order.id, transaction_ref='TX_DETERMINISTIC_LOCK')
        self.assertTrue(confirmed)
        self.assertEqual(reason, 'confirmed')

        self.product_a.refresh_from_db()
        self.product_b.refresh_from_db()
        # A doit être déduit de 1 + 2 = 3
        self.assertEqual(self.product_a.stock, initial_a - 3)
        # B doit être déduit de 2
        self.assertEqual(self.product_b.stock, initial_b - 2)

        # Exactement 3 mouvements de vente (un par ligne commandée)
        movements = StockMovement.objects.filter(order=order)
        self.assertEqual(movements.count(), 3)

    def test_12_repeated_identical_reference(self):
        """12. Une référence identique répétée sur une commande déjà payée est acceptée de façon idempotente."""
        from apps.orders.payment_processing import confirm_order_payment
        order = self._create_order(products_with_qty=[(self.product_a, 1)])

        # Première confirmation
        c1, o1, r1 = confirm_order_payment(order.id, transaction_ref='CP_REF_IDENTICAL')
        self.assertTrue(c1)
        self.assertEqual(o1.paygate_tx_id, 'CP_REF_IDENTICAL')

        # Seconde confirmation avec la MÊME référence
        c2, o2, r2 = confirm_order_payment(order.id, transaction_ref='CP_REF_IDENTICAL')
        self.assertFalse(c2)
        self.assertEqual(r2, 'already_paid')
        self.assertEqual(o2.paygate_tx_id, 'CP_REF_IDENTICAL')

    def test_13_different_reference_rejected_for_referenced_order(self):
        """13. Une référence différente soumise pour une commande déjà référencée est formellement rejetée."""
        from apps.orders.payment_processing import confirm_order_payment, PaymentProcessingError
        order = self._create_order(products_with_qty=[(self.product_a, 1)])

        c1, o1, r1 = confirm_order_payment(order.id, transaction_ref='CP_REF_ORIGINAL')
        self.assertTrue(c1)

        # Tentative avec une référence contradictoire
        with self.assertRaises(PaymentProcessingError) as ctx:
            confirm_order_payment(order.id, transaction_ref='CP_REF_CONTRADICTORY')

        self.assertIn("Incohérence de référence", str(ctx.exception))
        order.refresh_from_db()
        self.assertEqual(order.paygate_tx_id, 'CP_REF_ORIGINAL')

    def test_14_reference_already_used_by_another_order(self):
        """14. Une référence déjà associée à une autre commande est immédiatement rejetée (anti-collision)."""
        from apps.orders.payment_processing import confirm_order_payment, PaymentProcessingError
        order1 = self._create_order(products_with_qty=[(self.product_a, 1)])
        order2 = self._create_order(products_with_qty=[(self.product_b, 1)])

        # Order 1 consomme la référence
        confirm_order_payment(order1.id, transaction_ref='CP_SHARED_TX_999')

        # Order 2 tente d'utiliser la même référence
        with self.assertRaises(PaymentProcessingError) as ctx:
            confirm_order_payment(order2.id, transaction_ref='CP_SHARED_TX_999')

        self.assertIn("déjà associée", str(ctx.exception))
        order2.refresh_from_db()
        self.assertFalse(order2.payment_status)
        self.assertIsNone(order2.paygate_tx_id)

    def test_15_admin_fulfillment_failure_and_reprocessing(self):
        """15. Échec du fulfillment depuis l'administration (stock insuffisant) et reprise après réapprovisionnement."""
        from apps.products.models import Product
        from apps.orders.admin import OrderAdmin
        from django.contrib.admin.sites import AdminSite

        # Produit en rupture
        prod_empty = Product.objects.create(name='Produit Épuisé Admin', price=Decimal('1000'), stock=0)
        order = self._create_order(products_with_qty=[(prod_empty, 2)])

        # L'admin marque la commande comme paid
        order.status = 'paid'
        order.save()  # Déclenche handle_order_automation

        order.refresh_from_db()
        # Le statut est paid, mais stock_updated est False
        self.assertEqual(order.status, 'paid')
        self.assertFalse(order.stock_updated)
        # La note d'échec est présente
        self.assertIn("[ÉCHEC TRAITEMENT STOCK]", order.notes)

        # L'affichage admin signale clairement l'état incomplet
        admin_instance = OrderAdmin(Order, AdminSite())
        colored = admin_instance.colored_status(order)
        self.assertIn("PAYÉ (STOCK INCOMPLET)", colored)
        status_stk = admin_instance.status_stock(order)
        self.assertIn("⚠️ Incomplet", status_stk)

        # Maintenant, réapprovisionnement du produit en stock
        prod_empty.stock = 10
        prod_empty.save()

        # Action admin de retraitement
        from django.test import RequestFactory
        from django.contrib.sessions.middleware import SessionMiddleware
        from django.contrib.messages.middleware import MessageMiddleware

        factory = RequestFactory()
        request = factory.get('/admin/orders/order/')
        request.user = self.user
        SessionMiddleware(lambda req: None).process_request(request)
        MessageMiddleware(lambda req: None).process_request(request)
        admin_instance.reprocess_stock_for_paid_orders(request, Order.objects.filter(id=order.id))

        order.refresh_from_db()
        prod_empty.refresh_from_db()
        self.assertTrue(order.stock_updated)
        self.assertEqual(prod_empty.stock, 8)
        self.assertIn("[STOCK RÉGULARISÉ AVEC SUCCÈS]", order.notes)
