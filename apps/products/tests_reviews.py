"""
Tests automatisés pour le système d'avis clients de Venus Luna.
Couvre : dépôt, validation, achat vérifié, recalcul, modération, page d'accueil.
"""
from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth.models import User

from apps.products.models import Product, Category, Review
from apps.orders.models import Order, OrderItem


class ReviewModelTest(TestCase):
    """Tests unitaires sur le modèle Review et ses signaux."""

    def setUp(self):
        self.category = Category.objects.create(name="Cristaux", slug="cristaux")
        self.product = Product.objects.create(
            name="Améthyste", slug="amethyste",
            price=5000, stock=10, category=self.category
        )
        self.user = User.objects.create_user(username="testuser", password="pass1234", email="test@example.com")

    def test_review_creation(self):
        review = Review.objects.create(
            product=self.product, user=self.user,
            client_name="Koffi", rating=5, comment="Excellent produit !"
        )
        self.assertEqual(review.rating, 5)
        self.assertFalse(review.is_approved)

    def test_product_rating_cache_updated_on_approve(self):
        """Le cache average_rating/total_reviews doit se mettre à jour après approbation."""
        Review.objects.create(
            product=self.product, user=self.user,
            client_name="Koffi", rating=4, comment="Bien.",
            is_approved=True
        )
        self.product.refresh_from_db()
        self.assertEqual(self.product.total_reviews, 1)
        self.assertEqual(float(self.product.average_rating), 4.0)

    def test_product_rating_cache_zero_when_no_approved_reviews(self):
        """Aucun avis approuvé → note moyenne et total à 0."""
        Review.objects.create(
            product=self.product, user=self.user,
            client_name="Koffi", rating=5, comment="Super.",
            is_approved=False  # non approuvé, ne compte pas
        )
        self.product.refresh_from_db()
        self.assertEqual(self.product.total_reviews, 0)
        self.assertEqual(float(self.product.average_rating), 0.0)

    def test_multiple_reviews_average(self):
        user2 = User.objects.create_user(username="user2", password="pass1234")
        Review.objects.create(product=self.product, user=self.user, client_name="A", rating=5, comment="Top", is_approved=True)
        Review.objects.create(product=self.product, user=user2, client_name="B", rating=3, comment="Moyen", is_approved=True)
        self.product.refresh_from_db()
        self.assertEqual(self.product.total_reviews, 2)
        self.assertAlmostEqual(float(self.product.average_rating), 4.0, places=1)

    def test_review_deleted_updates_cache(self):
        review = Review.objects.create(
            product=self.product, user=self.user,
            client_name="Koffi", rating=5, comment="Super.", is_approved=True
        )
        self.product.refresh_from_db()
        self.assertEqual(self.product.total_reviews, 1)
        review.delete()
        self.product.refresh_from_db()
        self.assertEqual(self.product.total_reviews, 0)

    def test_unique_review_per_user_product(self):
        """Un même utilisateur ne peut pas laisser deux avis sur le même produit."""
        from django.db import IntegrityError
        Review.objects.create(product=self.product, user=self.user, client_name="Koffi", rating=5, comment="1er avis")
        with self.assertRaises(IntegrityError):
            Review.objects.create(product=self.product, user=self.user, client_name="Koffi", rating=4, comment="2ème avis")


class ReviewViewTest(TestCase):
    """Tests fonctionnels sur les vues de soumission d'avis."""

    def setUp(self):
        self.client = Client()
        self.category = Category.objects.create(name="Cristaux", slug="cristaux-v")
        self.product = Product.objects.create(
            name="Rose Quartz", slug="rose-quartz",
            price=4000, stock=5, category=self.category
        )
        self.user = User.objects.create_user(username="venus_user", password="securepass123")

    def test_submit_review_requires_login(self):
        """Un utilisateur non connecté est redirigé vers la page de connexion."""
        url = reverse('products:submit_review', args=[self.product.id])
        response = self.client.post(url, {'rating': 5, 'comment': 'Super', 'client_name': 'Test'})
        self.assertEqual(response.status_code, 302)
        self.assertIn('/accounts/login', response['Location'])

    def test_submit_review_logged_in(self):
        """Un utilisateur connecté peut soumettre un avis. Il est créé en statut non approuvé."""
        self.client.login(username='venus_user', password='securepass123')
        url = reverse('products:submit_review', args=[self.product.id])
        response = self.client.post(url, {
            'rating': '5',
            'comment': 'Produit exceptionnel !',
            'client_name': 'Venus User',
            'title': ''
        })
        self.assertEqual(response.status_code, 302)
        review = Review.objects.filter(product=self.product, user=self.user).first()
        self.assertIsNotNone(review)
        self.assertFalse(review.is_approved)  # En attente de modération

    def test_cannot_submit_duplicate_review(self):
        """Un deuxième avis pour le même produit doit être refusé."""
        self.client.login(username='venus_user', password='securepass123')
        Review.objects.create(product=self.product, user=self.user, client_name="V", rating=4, comment="Déjà posté")
        url = reverse('products:submit_review', args=[self.product.id])
        response = self.client.post(url, {'rating': '5', 'comment': 'Doublon', 'client_name': 'V'})
        # Doit rediriger avec message d'erreur, pas créer un second avis
        self.assertEqual(Review.objects.filter(product=self.product, user=self.user).count(), 1)


class VerifiedPurchaseTest(TestCase):
    """Tests sur la détection automatique de l'achat vérifié."""

    def setUp(self):
        self.user = User.objects.create_user(username="buyer", password="buyerpass")
        self.category = Category.objects.create(name="Encens", slug="encens-vp")
        self.product = Product.objects.create(name="Palo Santo", slug="palo-santo", price=2000, stock=10, category=self.category)

    def test_verified_purchase_detected(self):
        """Un client ayant une commande payée doit obtenir le badge vérifié."""
        from apps.products.views import check_verified_purchase
        order = Order.objects.create(user=self.user, payment_status=True, status='delivered', total=2000)
        OrderItem.objects.create(order=order, product=self.product, name=self.product.name, price=2000, quantity=1)
        self.assertTrue(check_verified_purchase(self.user, self.product))

    def test_unverified_purchase_without_order(self):
        """Un client sans commande ne doit PAS obtenir le badge vérifié."""
        from apps.products.views import check_verified_purchase
        self.assertFalse(check_verified_purchase(self.user, self.product))
