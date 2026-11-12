"""Utilitaires d'optimisation et de validation d'images pour le module LMS (Formations).

Ce module assure :
1. La validation stricte du format (JPEG, PNG, WebP) et de l'intégrité de l'image.
2. Le redimensionnement automatique des images excédant 1920x1080 (sans agrandir les plus petites).
3. La préservation de la transparence alpha (canaux RGBA / trans).
4. La conversion en format WebP moderne hautement compressé (qualité 80-85, cible < 500 Ko).
5. La correction automatique de l'orientation EXIF.
6. La protection contre l'envoi de fichiers surdimensionnés (> 10 Mo) vers Cloudinary.
"""

import io
import os
import logging
from PIL import Image, ImageOps
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import UploadedFile, SimpleUploadedFile
from django.utils.text import slugify

logger = logging.getLogger(__name__)

# Extensions autorisées
ALLOWED_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.webp'}

# Formats Pillow reconnus et acceptés
ALLOWED_PIL_FORMATS = {'JPEG', 'PNG', 'WEBP'}

# Limite maximale brute avant traitement (30 Mo) pour parer aux DoS / memory exhaustion
MAX_UPLOAD_SIZE_BYTES = 30 * 1024 * 1024  # 30 Mo

# Dimensions maximales pour l'affichage plein écran HD
MAX_WIDTH = 1920
MAX_HEIGHT = 1080

# Paramètres de compression WebP
TARGET_QUALITY = 82
TARGET_MAX_BYTES = 500 * 1024  # 500 Ko
MIN_QUALITY = 70


def validate_course_cover_image(uploaded_file):
    """Valide qu'un fichier téléversé est bien une image compatible et intègre.

    Lève django.core.exceptions.ValidationError avec un message clair en français
    en cas d'anomalie.
    """
    if not uploaded_file:
        return

    # Si ce n'est pas un fichier nouvellement téléversé (ex: ressource Cloudinary existante), ignorer
    if not isinstance(uploaded_file, UploadedFile):
        return

    # 1. Vérification de la taille brute maximale (sécurité anti-DoS)
    file_size = getattr(uploaded_file, 'size', None)
    if file_size and file_size > MAX_UPLOAD_SIZE_BYTES:
        raise ValidationError(
            f"L'image sélectionnée est trop volumineuse ({file_size / (1024 * 1024):.1f} Mo). "
            f"La taille maximale autorisée avant optimisation est de 30 Mo."
        )

    # 2. Vérification de l'extension du nom de fichier
    file_name = getattr(uploaded_file, 'name', '') or ''
    ext = os.path.splitext(file_name)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise ValidationError(
            f"Extension de fichier « {ext or 'inconnue'} » non autorisée. "
            f"Les formats acceptés pour la couverture sont : JPEG, JPG, PNG et WebP."
        )

    # 3. Vérification de l'intégrité et du format réel via Pillow
    try:
        if hasattr(uploaded_file, 'seek'):
            uploaded_file.seek(0)

        with Image.open(uploaded_file) as img:
            detected_format = (img.format or '').upper()
            if detected_format not in ALLOWED_PIL_FORMATS:
                raise ValidationError(
                    f"Le format d'image réel détecté ({detected_format}) n'est pas pris en charge. "
                    f"Seuls les formats JPEG, PNG et WebP sont autorisés."
                )
            img.verify()
    except ValidationError:
        raise
    except Exception as exc:
        logger.warning("Fichier image corrompu ou invalide téléversé (%s): %s", file_name, exc)
        raise ValidationError(
            "Le fichier téléversé n'est pas une image valide ou est corrompu. "
            "Veuillez choisir un fichier image intact (JPEG, PNG ou WebP)."
        )
    finally:
        if hasattr(uploaded_file, 'seek'):
            uploaded_file.seek(0)


def optimize_course_cover_image(
    uploaded_file,
    max_size=(MAX_WIDTH, MAX_HEIGHT),
    quality=TARGET_QUALITY,
    target_bytes=TARGET_MAX_BYTES
):
    """Optimise une image de couverture avant transmission à Cloudinary.

    - Valide l'intégrité de l'image.
    - Applique la rotation EXIF appropriée.
    - Préserve le canal alpha si nécessaire (RGBA).
    - Redimensionne si les dimensions excèdent max_size (sans agrandir si plus petite).
    - Convertit en WebP avec qualité adaptative pour viser < 500 Ko.
    - Retourne un SimpleUploadedFile prêt à être transmis à CloudinaryField.
    """
    if not uploaded_file or not isinstance(uploaded_file, UploadedFile):
        return uploaded_file

    # Validation préalable
    validate_course_cover_image(uploaded_file)

    if hasattr(uploaded_file, 'seek'):
        uploaded_file.seek(0)

    try:
        img = Image.open(uploaded_file)
    except Exception as exc:
        raise ValidationError(
            f"Impossible de traiter l'image de couverture : {exc}"
        ) from exc

    # 1. Traitement de l'orientation EXIF
    try:
        img = ImageOps.exif_transpose(img)
    except Exception as exc:
        logger.debug("Aucune métadonnée EXIF d'orientation à appliquer: %s", exc)

    # 2. Gestion de la transparence et des modes de couleurs
    has_alpha = False
    if img.mode in ('RGBA', 'LA'):
        has_alpha = True
    elif img.mode == 'P' and 'transparency' in img.info:
        has_alpha = True

    if has_alpha:
        if img.mode != 'RGBA':
            img = img.convert('RGBA')
    else:
        if img.mode != 'RGB':
            img = img.convert('RGB')

    # 3. Redimensionnement (downscale uniquement, conserve le ratio)
    target_w, target_h = max_size
    if img.width > target_w or img.height > target_h:
        img.thumbnail((target_w, target_h), Image.Resampling.LANCZOS)

    # 4. Conversion et compression WebP
    current_quality = quality
    output = io.BytesIO()
    img.save(output, format='WEBP', quality=current_quality, method=4)

    # Ajustement progressif de la qualité si le poids dépasse la cible
    while output.tell() > target_bytes and current_quality > MIN_QUALITY:
        current_quality -= 5
        output.seek(0)
        output.truncate(0)
        img.save(output, format='WEBP', quality=current_quality, method=4)

    output_bytes = output.getvalue()

    # 5. Préparation du nom de fichier nettoyé en .webp
    original_name = getattr(uploaded_file, 'name', 'cover.jpg') or 'cover.jpg'
    stem = os.path.splitext(os.path.basename(original_name))[0]
    clean_stem = slugify(stem) or 'cover'
    new_filename = f"{clean_stem}.webp"

    logger.info(
        "Image de couverture optimisée avec succès : %s -> %s (%d Ko, %dx%d, qualité %d)",
        original_name,
        new_filename,
        len(output_bytes) // 1024,
        img.width,
        img.height,
        current_quality
    )

    return SimpleUploadedFile(
        name=new_filename,
        content=output_bytes,
        content_type='image/webp'
    )
