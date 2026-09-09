"""
settings_test.py - Settings minimaux pour les tests locaux.
Herite de config.settings et remplace la DB par SQLite en memoire.

Usage :
    python manage.py test apps.accounts.tests --settings=config.settings_test
"""
from config.settings import *  # noqa: F401, F403

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }
}

SECRET_KEY = "test-secret-key-for-unit-tests-only"

EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
SECURE_SSL_REDIRECT = False
DEFAULT_FILE_STORAGE = "django.core.files.storage.FileSystemStorage"

# Validateurs de mots de passe Django standards (absents de settings.py principal)
# Requis pour que PasswordChangeForm rejette les mots de passe faibles (test_cas3)
AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {"min_length": 8},
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]

# Accélérateur de tests : hachage MD5 ultra-rapide pour les tests
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.MD5PasswordHasher",
]

