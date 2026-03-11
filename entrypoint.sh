#!/bin/sh
set -e

# Créer les répertoires media s'ils n'existent pas
mkdir -p /app/media
mkdir -p /app/media/blog
mkdir -p /app/media/core
mkdir -p /app/media/products
mkdir -p /app/media/avatars

# Appliquer les permissions corrects (écriture pour tous)
chmod -R 777 /app/media

python manage.py migrate --noinput

exec gunicorn config.wsgi:application --bind 0.0.0.0:8000

