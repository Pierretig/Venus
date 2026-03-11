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

# Utilisateur non-root
RUN adduser --disabled-password --gecos '' appuser && chown -R appuser /app
USER appuser

ENV DJANGO_SETTINGS_MODULE=config.settings

# Point d'entrée : migrations puis lancement de Gunicorn
ENTRYPOINT ["./entrypoint.sh"]

