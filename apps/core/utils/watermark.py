"""
Utilitaires pour générer des URLs Cloudinary avec ou sans watermark.
"""

import cloudinary
import cloudinary.utils
from django.conf import settings

WATERMARK_TEXT = getattr(settings, 'WATERMARK_TEXT', 'Venus-Luna')


def get_clean_url(public_id):
    """
    Retourne l'URL Cloudinary normale, sans aucune transformation.
    Utilisée pour l'affichage des images sur le site (via le proxy).
    """
    if not public_id:
        return ''
    url, _ = cloudinary.utils.cloudinary_url(
        public_id,
        secure=True,
    )
    return url


def get_watermarked_url(public_id):
    """
    Retourne l'URL Cloudinary avec watermark texte 'Venus-Luna'
    répété en pattern diagonal sur toute l'image (tiled).

    Style : texte Arial 50px bold, blanc, opacité 25%, incliné -30°.
    """
    if not public_id:
        return ''

    transformation = [
        {
            'overlay': {
                'font_family': 'Arial',
                'font_size': 50,
                'font_weight': 'bold',
                'text': WATERMARK_TEXT,
            },
            'color': '#FFFFFF',
            'opacity': 25,
            'angle': -30,
            'flags': 'tiled',
        }
    ]

    url, _ = cloudinary.utils.cloudinary_url(
        public_id,
        transformation=transformation,
        secure=True,
    )
    return url

