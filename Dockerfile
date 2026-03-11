FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Dépendances système pour PostgreSQL et Pillow
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    libjpeg-dev \
    zlib1g-dev \
    nginx \
    curl \
  && rm -rf /var/lib/apt/lists/*

# Installation des dépendances Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copie du code de l'application
COPY . .

# Rendre le script d'entrée exécutable
RUN chmod +x entrypoint.sh

# Collecte des fichiers statiques
RUN python manage.py collectstatic --noinput

# Créer les répertoires media AVANT de changer d'utilisateur
RUN mkdir -p /app/media /app/media/blog /app/media/core /app/media/products /app/media/avatars

# Créer un groupe www-data et utilisateur pour les permissions de volume
RUN groupadd -g 1000 www-data || true && \
    useradd -r -s /bin/bash -g www-data appuser || true && \
    chown -R www-data:www-data /app/media && \
    chmod -R 775 /app/media

# permissions pour le répertoire staticfiles
RUN chown -R appuser:appuser /app/staticfiles

# Utilisateur avec accès au groupe www-data pour le montage de volume
USER appuser

ENV DJANGO_SETTINGS_MODULE=config.settings

# Point d'entrée : migrations puis lancement de Gunicorn
ENTRYPOINT ["./entrypoint.sh"]

