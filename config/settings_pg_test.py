"""
settings_pg_test.py — Tests sur PostgreSQL LOCAL (concurrence, verrous, triggers, contraintes).

Usage :
    python manage.py test --settings=config.settings_pg_test

Variables (facultatives) : PG_TEST_NAME, PG_TEST_USER, PG_TEST_PASSWORD, PG_TEST_HOST, PG_TEST_PORT.
Par défaut : base « venus_luna_localtest », rôle « postgres », 127.0.0.1:5432.
Le runner de tests Django crée puis détruit « test_<PG_TEST_NAME> ».

Sécurité : refuse de démarrer si l'hôte n'est pas local. Les variables DB_* / DATABASE_URL
du fichier .env (qui peuvent viser une base distante) sont ignorées ici.
"""
import os

from config.settings import *  # noqa: F401, F403

_host = os.environ.get("PG_TEST_HOST", "127.0.0.1")
if _host not in ("127.0.0.1", "localhost", "::1"):
    raise RuntimeError(f"settings_pg_test : hôte non local refusé ({_host}).")

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.environ.get("PG_TEST_NAME", "venus_luna_localtest"),
        "USER": os.environ.get("PG_TEST_USER", "postgres"),
        "PASSWORD": os.environ.get("PG_TEST_PASSWORD", ""),
        "HOST": _host,
        "PORT": os.environ.get("PG_TEST_PORT", "5432"),
        "TEST": {"NAME": "test_" + os.environ.get("PG_TEST_NAME", "venus_luna_localtest")},
    }
}

DEBUG = False
EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
SECURE_SSL_REDIRECT = False
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False
DEFAULT_FILE_STORAGE = "django.core.files.storage.FileSystemStorage"
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
