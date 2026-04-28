"""
Tests du système de watermark intelligent.
"""

from django.test import TestCase, RequestFactory, override_settings
from django.urls import reverse
from django.apps import apps
from unittest.mock import patch, MagicMock
from apps.core.views import serve_image
from apps.core.utils.watermark import get_clean_url, get_watermarked_url


class WatermarkUrlUtilsTest(TestCase):
    """Tests des fonctions utilitaires de génération d'URL."""

    @patch('apps.core.utils.watermark.cloudinary.utils.cloudinary_url')
    def test_get_clean_url(self, mock_cloudinary_url):
        mock_cloudinary_url.return_value = ('https://res.cloudinary.com/demo/image/upload/v123/test.jpg', {})
        url = get_clean_url('products/test_image')
        self.assertEqual(url, 'https://res.cloudinary.com/demo/image/upload/v123/test.jpg')
        mock_cloudinary_url.assert_called_once_with('products/test_image', secure=True)

    @patch('apps.core.utils.watermark.cloudinary.utils.cloudinary_url')
    def test_get_watermarked_url(self, mock_cloudinary_url):
        mock_cloudinary_url.return_value = ('https://res.cloudinary.com/demo/image/upload/l_text:Arial_50_bold:Venus-Luna,co_white,o_25,a_-30,fl_tiled/v123/test.jpg', {})
        url = get_watermarked_url('products/test_image')
        self.assertIn('l_text', url)
        mock_cloudinary_url.assert_called_once()
        _, kwargs = mock_cloudinary_url.call_args
        self.assertIn('transformation', kwargs)
        self.assertEqual(kwargs['secure'], True)

    def test_empty_public_id_returns_empty_string(self):
        self.assertEqual(get_clean_url(''), '')
        self.assertEqual(get_clean_url(None), '')
        self.assertEqual(get_watermarked_url(''), '')
        self.assertEqual(get_watermarked_url(None), '')


@override_settings(SITE_DOMAIN='venus-luna.com')
class ServeImageViewTest(TestCase):
    """Tests de la vue proxy serve_image."""

    def setUp(self):
        self.factory = RequestFactory()
        # On mock la récupération du modèle et de l'instance
        # pour ne pas dépendre de la base de données réelle.
        self.mock_instance = MagicMock()
        self.mock_instance.pk = 1
        self.mock_instance.image = 'products/test_image'

    @patch('apps.core.views.apps.get_model')
    @patch('apps.core.views.get_object_or_404')
    @patch('apps.core.views.get_clean_url')
    @patch('apps.core.views.get_watermarked_url')
    def test_internal_referer_returns_clean_url(self, mock_wm, mock_clean, mock_get_obj, mock_get_model):
        mock_clean.return_value = 'https://res.cloudinary.com/clean.jpg'
        mock_get_obj.return_value = self.mock_instance
        mock_get_model.return_value = MagicMock()

        request = self.factory.get(
            '/media/image/products/productimage/1/image/',
            HTTP_REFERER='https://venus-luna.com/produits/'
        )
        response = serve_image(request, 'products', 'productimage', 1, 'image')

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response['Location'], 'https://res.cloudinary.com/clean.jpg')
        mock_clean.assert_called_once_with('products/test_image')
        mock_wm.assert_not_called()

    @patch('apps.core.views.apps.get_model')
    @patch('apps.core.views.get_object_or_404')
    @patch('apps.core.views.get_clean_url')
    @patch('apps.core.views.get_watermarked_url')
    def test_no_referer_returns_watermarked_url(self, mock_wm, mock_clean, mock_get_obj, mock_get_model):
        mock_wm.return_value = 'https://res.cloudinary.com/watermarked.jpg'
        mock_get_obj.return_value = self.mock_instance
        mock_get_model.return_value = MagicMock()

        request = self.factory.get('/media/image/products/productimage/1/image/')
        response = serve_image(request, 'products', 'productimage', 1, 'image')

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response['Location'], 'https://res.cloudinary.com/watermarked.jpg')
        mock_wm.assert_called_once_with('products/test_image')
        mock_clean.assert_not_called()

    @patch('apps.core.views.apps.get_model')
    @patch('apps.core.views.get_object_or_404')
    @patch('apps.core.views.get_clean_url')
    @patch('apps.core.views.get_watermarked_url')
    def test_external_referer_returns_watermarked_url(self, mock_wm, mock_clean, mock_get_obj, mock_get_model):
        mock_wm.return_value = 'https://res.cloudinary.com/watermarked.jpg'
        mock_get_obj.return_value = self.mock_instance
        mock_get_model.return_value = MagicMock()

        request = self.factory.get(
            '/media/image/products/productimage/1/image/',
            HTTP_REFERER='https://pirate-site.com/'
        )
        response = serve_image(request, 'products', 'productimage', 1, 'image')

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response['Location'], 'https://res.cloudinary.com/watermarked.jpg')
        mock_wm.assert_called_once()
        mock_clean.assert_not_called()

    @patch('apps.core.views.apps.get_model')
    @patch('apps.core.views.get_object_or_404')
    @patch('apps.core.views.get_clean_url')
    @patch('apps.core.views.get_watermarked_url')
    def test_curl_user_agent_returns_watermarked_url(self, mock_wm, mock_clean, mock_get_obj, mock_get_model):
        mock_wm.return_value = 'https://res.cloudinary.com/watermarked.jpg'
        mock_get_obj.return_value = self.mock_instance
        mock_get_model.return_value = MagicMock()

        request = self.factory.get(
            '/media/image/products/productimage/1/image/',
            HTTP_USER_AGENT='curl/7.68.0',
            HTTP_REFERER='https://venus-luna.com/'  # même avec un bon referer, curl doit être bloqué
        )
        response = serve_image(request, 'products', 'productimage', 1, 'image')

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response['Location'], 'https://res.cloudinary.com/watermarked.jpg')
        mock_wm.assert_called_once()
        mock_clean.assert_not_called()

    @patch('apps.core.views.apps.get_model')
    @patch('apps.core.views.get_object_or_404')
    @patch('apps.core.views.get_clean_url')
    @patch('apps.core.views.get_watermarked_url')
    def test_wget_user_agent_returns_watermarked_url(self, mock_wm, mock_clean, mock_get_obj, mock_get_model):
        mock_wm.return_value = 'https://res.cloudinary.com/watermarked.jpg'
        mock_get_obj.return_value = self.mock_instance
        mock_get_model.return_value = MagicMock()

        request = self.factory.get(
            '/media/image/products/productimage/1/image/',
            HTTP_USER_AGENT='Wget/1.21.1'
        )
        response = serve_image(request, 'products', 'productimage', 1, 'image')

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response['Location'], 'https://res.cloudinary.com/watermarked.jpg')
        mock_wm.assert_called_once()


class UrlExposureTest(TestCase):
    """Vérifie que le public_id Cloudinary n'apparaît jamais dans les URLs internes."""

    def test_serve_image_url_structure(self):
        """L'URL interne doit utiliser le modèle et la PK, jamais le public_id Cloudinary."""
        url = reverse('core:serve_image', kwargs={
            'app_label': 'products',
            'model_name': 'productimage',
            'pk': 42,
            'field_name': 'image',
        })
        self.assertIn('/media/image/', url)
        self.assertNotIn('cloudinary', url)
        self.assertNotIn('res.cloudinary.com', url)
        self.assertNotIn('products/test_image', url)

    def test_url_does_not_contain_public_id(self):
        """La PK Django et le nom du modèle suffisent ; aucun public_id ne fuite."""
        url = reverse('core:serve_image', kwargs={
            'app_label': 'blog',
            'model_name': 'post',
            'pk': 99,
            'field_name': 'image',
        })
        # L'URL doit être propre et générique
        expected_pattern = '/media/image/blog/post/99/image/'
        self.assertEqual(url, expected_pattern)

