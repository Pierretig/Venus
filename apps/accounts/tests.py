from django.test import TestCase, Client, override_settings
from django.urls import reverse
from django.contrib.auth.models import User
from django.contrib.auth import authenticate


CHANGE_PASSWORD_URL = '/accounts/mon-compte/changer-mot-de-passe/'


@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
class ChangePasswordViewTests(TestCase):
    """
    Tests de la fonctionnalité de changement de mot de passe.
    Couvre les 8 cas de sécurité requis.
    """

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username='testvenus',
            email='testvenus@venus-luna.com',
            password='AncienMotDePasse123!',
        )
        self.url = CHANGE_PASSWORD_URL
        self.login_url = reverse('accounts:login')

    # ------------------------------------------------------------------
    # Cas 1 — Utilisateur non connecté → redirection vers la connexion
    # ------------------------------------------------------------------
    def test_cas1_acces_refuse_utilisateur_non_connecte_get(self):
        """GET sans session → redirection vers la page de connexion."""
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 302)
        self.assertIn('/accounts/login/', response['Location'])

    def test_cas1_acces_refuse_utilisateur_non_connecte_post(self):
        """POST sans session → redirection vers la page de connexion (pas de changement)."""
        response = self.client.post(self.url, {
            'old_password': 'AncienMotDePasse123!',
            'new_password1': 'NouveauMotDePasse456!',
            'new_password2': 'NouveauMotDePasse456!',
        })
        self.assertEqual(response.status_code, 302)
        self.assertIn('/accounts/login/', response['Location'])
        # Le mot de passe ne doit pas avoir changé
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password('AncienMotDePasse123!'))

    # ------------------------------------------------------------------
    # Cas 2 — Mauvais mot de passe actuel → modification refusée
    # ------------------------------------------------------------------
    def test_cas2_mauvais_mot_de_passe_actuel(self):
        """POST avec un mauvais old_password → formulaire invalide, mdp inchangé."""
        self.client.login(username='testvenus', password='AncienMotDePasse123!')
        response = self.client.post(self.url, {
            'old_password': 'MauvaisMotDePasse999!',
            'new_password1': 'NouveauMotDePasse456!',
            'new_password2': 'NouveauMotDePasse456!',
        })
        # Réaffichage du formulaire (200, pas de redirect)
        self.assertEqual(response.status_code, 200)
        # Le mot de passe ne doit pas avoir changé
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password('AncienMotDePasse123!'))

    # ------------------------------------------------------------------
    # Cas 3 — Nouveau mot de passe invalide (trop court) → refus
    # ------------------------------------------------------------------
    def test_cas3_nouveau_mot_de_passe_invalide(self):
        """POST avec un nouveau mdp trop court → formulaire invalide."""
        self.client.login(username='testvenus', password='AncienMotDePasse123!')
        response = self.client.post(self.url, {
            'old_password': 'AncienMotDePasse123!',
            'new_password1': 'abc',  # Trop court
            'new_password2': 'abc',
        })
        self.assertEqual(response.status_code, 200)
        # Le mot de passe ne doit pas avoir changé
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password('AncienMotDePasse123!'))

    # ------------------------------------------------------------------
    # Cas 4 — Confirmation différente → modification refusée
    # ------------------------------------------------------------------
    def test_cas4_confirmation_differente(self):
        """POST avec new_password1 != new_password2 → formulaire invalide."""
        self.client.login(username='testvenus', password='AncienMotDePasse123!')
        response = self.client.post(self.url, {
            'old_password': 'AncienMotDePasse123!',
            'new_password1': 'NouveauMotDePasse456!',
            'new_password2': 'MotDePasseDifferent789!',
        })
        self.assertEqual(response.status_code, 200)
        # Le mot de passe ne doit pas avoir changé
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password('AncienMotDePasse123!'))

    # ------------------------------------------------------------------
    # Cas 5 — Modification réussie → nouveau mot de passe enregistré
    # ------------------------------------------------------------------
    def test_cas5_modification_reussie(self):
        """POST valide → redirect vers dashboard, nouveau mdp enregistré en base."""
        self.client.login(username='testvenus', password='AncienMotDePasse123!')
        response = self.client.post(self.url, {
            'old_password': 'AncienMotDePasse123!',
            'new_password1': 'NouveauMotDePasse456!',
            'new_password2': 'NouveauMotDePasse456!',
        })
        # Doit rediriger vers le dashboard
        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse('accounts:client_dashboard'))
        # Le nouveau mdp doit être valide en base
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password('NouveauMotDePasse456!'))

    # ------------------------------------------------------------------
    # Cas 6 — L'ancien mot de passe ne permet plus de se connecter
    # ------------------------------------------------------------------
    def test_cas6_ancien_mot_de_passe_invalide_apres_changement(self):
        """Après changement, authenticate() avec l'ancien mdp doit retourner None."""
        self.client.login(username='testvenus', password='AncienMotDePasse123!')
        self.client.post(self.url, {
            'old_password': 'AncienMotDePasse123!',
            'new_password1': 'NouveauMotDePasse456!',
            'new_password2': 'NouveauMotDePasse456!',
        })
        self.user.refresh_from_db()
        result = authenticate(username='testvenus', password='AncienMotDePasse123!')
        self.assertIsNone(result, "L'ancien mot de passe ne doit plus être valide.")

    # ------------------------------------------------------------------
    # Cas 7 — Le nouveau mot de passe permet de se connecter
    # ------------------------------------------------------------------
    def test_cas7_nouveau_mot_de_passe_valide_pour_connexion(self):
        """Après changement, authenticate() avec le nouveau mdp doit retourner l'utilisateur."""
        self.client.login(username='testvenus', password='AncienMotDePasse123!')
        self.client.post(self.url, {
            'old_password': 'AncienMotDePasse123!',
            'new_password1': 'NouveauMotDePasse456!',
            'new_password2': 'NouveauMotDePasse456!',
        })
        self.user.refresh_from_db()
        result = authenticate(username='testvenus', password='NouveauMotDePasse456!')
        self.assertIsNotNone(result, "Le nouveau mot de passe doit permettre la connexion.")
        self.assertEqual(result, self.user)

    # ------------------------------------------------------------------
    # Cas 8 — Session maintenue après changement (pas de déconnexion forcée)
    # ------------------------------------------------------------------
    def test_cas8_session_maintenue_apres_changement(self):
        """
        Après un changement réussi, l'utilisateur reste connecté.
        update_session_auth_hash() est responsable de ce comportement.
        """
        self.client.login(username='testvenus', password='AncienMotDePasse123!')
        # Récupère la session avant le changement
        session_key_before = self.client.session.session_key

        self.client.post(self.url, {
            'old_password': 'AncienMotDePasse123!',
            'new_password1': 'NouveauMotDePasse456!',
            'new_password2': 'NouveauMotDePasse456!',
        })

        # L'accès au dashboard doit être possible (session active)
        dashboard_response = self.client.get(reverse('accounts:client_dashboard'))
        self.assertEqual(
            dashboard_response.status_code, 200,
            "L'utilisateur doit rester connecté après le changement de mot de passe."
        )
        # La session doit encore exister (pas détruite)
        self.assertIn('_auth_user_id', self.client.session)

    # ------------------------------------------------------------------
    # Sécurité supplémentaire : vérification CSRF implicite
    # ------------------------------------------------------------------
    def test_page_change_password_accessible_utilisateur_connecte(self):
        """GET avec session → 200 OK, template correct."""
        self.client.login(username='testvenus', password='AncienMotDePasse123!')
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'accounts/change_password.html')

    def test_impossible_modifier_mot_de_passe_autre_utilisateur(self):
        """
        La vue utilise request.user → impossible de cibler un autre utilisateur.
        Un utilisateur mal intentionné ne peut pas modifier le mdp d'autrui.
        """
        other_user = User.objects.create_user(
            username='autreuser',
            email='autre@venus-luna.com',
            password='MotDePasseAutre123!',
        )
        self.client.login(username='testvenus', password='AncienMotDePasse123!')
        # Tente un POST avec un vieux mdp de l'autre utilisateur
        self.client.post(self.url, {
            'old_password': 'MotDePasseAutre123!',
            'new_password1': 'NouveauMotDePasse456!',
            'new_password2': 'NouveauMotDePasse456!',
        })
        # Le mdp de l'autre utilisateur ne doit pas avoir changé
        other_user.refresh_from_db()
        self.assertTrue(
            other_user.check_password('MotDePasseAutre123!'),
            "Le mot de passe d'un autre utilisateur ne doit pas être modifié."
        )


class AccountsSecurityHardeningTests(TestCase):
    """Tests du durcissement de sécurité des comptes."""

    def test_password_reset_timeout_is_one_hour(self):
        """Vérifie que la durée de vie du token de réinitialisation est bien de 3600s (1h)."""
        from django.conf import settings
        self.assertEqual(settings.PASSWORD_RESET_TIMEOUT, 3600)

    def test_login_rate_limiting_blocks_after_threshold(self):
        """Vérifie que le rate limiting bloque après 5 tentatives de connexion par minute."""
        from django.core.cache import cache
        cache.clear()
        client = Client()
        login_url = reverse('accounts:login')

        # 5 premières tentatives échouées
        for i in range(5):
            response = client.post(login_url, {'username': f'baduser_{i}', 'password': 'badpassword'})
            self.assertEqual(response.status_code, 200)

        # 6e tentative -> doit être bloquée par le rate limit (redirect avec message d'erreur)
        response_blocked = client.post(login_url, {'username': 'baduser_6', 'password': 'badpassword'}, follow=True)
        messages_list = [str(m) for m in response_blocked.context['messages']]
        self.assertTrue(any('Trop de tentatives' in m for m in messages_list))

    def test_user_profile_form_avatar_size_validation(self):
        """Vérifie que le formulaire rejette les avatars dépassant 2 Mo."""
        import io
        from PIL import Image
        from django.core.files.uploadedfile import SimpleUploadedFile
        from apps.accounts.forms import UserProfileForm

        # Création d'une image PNG valide paddée à 2.5 Mo
        img = Image.new('RGB', (20, 20), color='green')
        buf = io.BytesIO()
        img.save(buf, format='PNG')
        oversized_content = buf.getvalue() + b' ' * (int(2.5 * 1024 * 1024))

        oversized_file = SimpleUploadedFile(
            'big_avatar.png',
            oversized_content,
            content_type='image/png'
        )

        form = UserProfileForm(
            data={'first_name': 'Test', 'last_name': 'User', 'email': 'test@venus-luna.com'},
            files={'avatar': oversized_file}
        )
        self.assertFalse(form.is_valid())
        self.assertIn('avatar', form.errors)
        self.assertTrue(any('2 Mo' in err for err in form.errors['avatar']))

    def test_user_profile_email_cannot_be_tampered(self):
        """Vérifie que l'adresse email de l'utilisateur ne peut pas être modifiée via edit_profile."""
        client = Client()
        user = User.objects.create_user(
            username='user_tamper',
            email='legitimate@venus-luna.com',
            password='Password123!'
        )
        client.login(username='user_tamper', password='Password123!')
        url = reverse('accounts:profile_edit')

        # Tentative de falsification de l'email via requête POST
        response = client.post(url, {
            'first_name': 'HackedName',
            'last_name': 'HackedLast',
            'email': 'evil_hijack@venus-luna.com',
            'phone': '+22890000000',
            'address': 'Quartier Test'
        })
        self.assertEqual(response.status_code, 302)

        user.refresh_from_db()
        # Le nom doit avoir changé, mais l'email DOIT être resté intact
        self.assertEqual(user.first_name, 'HackedName')
        self.assertEqual(user.email, 'legitimate@venus-luna.com')

    def test_logout_ignores_get_request(self):
        """Protection CSRF Logout : une requête GET ne déconnecte pas l'utilisateur."""
        client = Client()
        user = User.objects.create_user(
            username='user_logout_test',
            email='logout_test@venus-luna.com',
            password='Password123!'
        )
        client.login(username='user_logout_test', password='Password123!')
        logout_url = reverse('accounts:logout')

        # Requête GET sur la déconnexion
        response = client.get(logout_url)
        self.assertEqual(response.status_code, 302)

        # L'utilisateur doit toujours être connecté
        dashboard_response = client.get(reverse('accounts:client_dashboard'))
        self.assertEqual(dashboard_response.status_code, 200)

