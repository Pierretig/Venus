#!/bin/sh
set -e

# Créer les répertoires media s'ils n'existent pas
mkdir -p /app/media
mkdir -p /app/media/blog
mkdir -p /app/media/core
mkdir -p /app/media/products
mkdir -p /app/media/avatars

# Appliquer les permissions corrects pour le montage de volume
# Le groupe www-data (GID 1000) est utilisé pour la compatibilité avec Hostinger
chown -R appuser:www-data /app/media 2>/dev/null || true
chmod -R 775 /app/media 2>/dev/null || true

python manage.py migrate --noinput

exec gunicorn config.wsgi:application --bind 0.0.0.0:8000

