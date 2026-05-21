import os
from pathlib import Path
import sys
from urllib.parse import urlparse

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, os.path.join(BASE_DIR, 'apps'))


def load_fallback_env(env_path: Path) -> None:
    """
    Tente de récupérer des variables même si le .env utilise
    accidentellement le format `KEY: value` au lieu de `KEY=value`.
    """
    if not env_path.exists():
        return

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            key, value = line.split("=", 1)
        elif ":" in line:
            key, value = line.split(":", 1)
        else:
            continue
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


# Chargement du fichier .env (format standard + tolérance KEY: value)
load_fallback_env(BASE_DIR / ".env")

# --- SITE ID pour Django Sites (SEO) ---
SITE_ID = 1

# --- SÉCURITÉ (Utilise les variables d'environnement / .env en local) ---
SECRET_KEY = os.getenv('SECRET_KEY', 'u49lvqEsH5hTNlBcq7cuAq7yoXdgRjww35qxrn-sFrcugL2K6QyuqhV6vphkKD6L-IA')
DEBUG = os.getenv('DEBUG', 'False').strip().lower() in {'1', 'true', 'yes', 'on'}

# PROD LOGGING pour debug 502 errors
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '{levelname} {asctime} {module} {process:d} {thread:d} {message}',
            'style': '{',
        },
    },
    'handlers': {
        'console': {
            'level': 'INFO',
            'class': 'logging.StreamHandler',
            'formatter': 'verbose',
        },
        'file': {
            'level': 'ERROR',
            'class': 'logging.FileHandler',
            'filename': 'django.log',
            'formatter': 'verbose',
        },
    },
    'root': {
        'handlers': ['console'],
        'level': 'INFO',
    },
    'loggers': {
        'django': {
            'handlers': ['console'],
            'level': 'INFO',
            'propagate': False,
        },
        'django.db.backends': {
            'level': 'ERROR',
            'handlers': ['console'],
        },
    },
}

ALLOWED_HOSTS = os.getenv('ALLOWED_HOSTS', '127.0.0.1,localhost').split(',')
ALLOWED_HOSTS = [h.strip() for h in ALLOWED_HOSTS if h.strip()]
if not DEBUG:
    ALLOWED_HOSTS.append('*')  # Temporaire pour prod, restreindre après

# --- CORRECTION CSRF PRODUCTION ---
CSRF_TRUSTED_ORIGINS = [
    "https://venus-luna.com",
    "https://www.venus-luna.com"
]

SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

# Derrière Traefik / Nginx / Dokploy : Host et schéma réels pour redirections correctes
if not DEBUG:
    USE_X_FORWARDED_HOST = True

# Chemins exemptés de la redirection HTTP→HTTPS (sondes internes sans en-têtes proxy)
SECURE_REDIRECT_EXEMPT = [r'^health/?$']

# HTTPS/SSL Settings pour SEO (uniquement en production)
if not DEBUG:
    SECURE_SSL_REDIRECT = True  # Redirect HTTP to HTTPS
    SECURE_HSTS_SECONDS = 31536000  # 1 year
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
else:
    SECURE_SSL_REDIRECT = False
    
CSRF_COOKIE_SECURE = not DEBUG
SESSION_COOKIE_SECURE = not DEBUG

# --- CONFIGURATION PAYPLUS AFRICA ---
PAYPLUS_API_KEY = os.getenv('PAYPLUS_API_KEY')
PAYPLUS_MERCHANT_ID = os.getenv('PAYPLUS_MERCHANT_ID')
SITE_URL = os.getenv('SITE_URL', 'https://venus-luna.com')
PAYPLUS_WEBHOOK_URL = f"{SITE_URL}/orders/webhook/payplus/"

# --- CONFIGURATION WATERMARK CLOUDINARY ---
WATERMARK_TEXT = os.getenv('WATERMARK_TEXT', 'Venus-Luna')
SITE_DOMAIN = os.getenv('SITE_DOMAIN', 'venus-luna.com')

# --- APPLICATIONS ---
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.sitemaps',  # Pour le SEO
    'django.contrib.sites',  # Pour le SEO (requis pour sitemaps)
    'apps.accounts',
    'apps.products',
    'apps.orders',
    'apps.blog',
    'apps.contact',
    'apps.core',
    'admin_custom',
    "jazzmin",
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'apps.core.context_processors.global_data',
            ],
            'builtins': [
                'apps.core.templatetags.cloudinary_extras',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'

def parse_database_url(db_url: str) -> dict:
    parsed = urlparse(db_url)
    if parsed.scheme not in {"postgres", "postgresql"}:
        raise ValueError("DATABASE_URL doit être en postgres/postgresql.")

    db_name = parsed.path.lstrip("/")
    if not db_name:
        raise ValueError("DATABASE_URL ne contient pas de nom de base.")

    return {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": db_name,
        "USER": parsed.username or "",
        "PASSWORD": parsed.password or "",
        "HOST": parsed.hostname or "",
        "PORT": str(parsed.port or 5432),
    }


def get_database_config() -> dict:
    # Préférer DB_* si complet : évite DATABASE_URL invalide (ex. @ non encodé dans le mot de passe)
    db_name = os.getenv("DB_NAME")
    db_user = os.getenv("DB_USER")
    db_password = os.getenv("DB_PASSWORD", "")
    db_host = os.getenv("DB_HOST")
    db_port = os.getenv("DB_PORT", "5432")
    if db_name and db_user and db_host:
        return {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": db_name,
            "USER": db_user,
            "PASSWORD": db_password,
            "HOST": db_host,
            "PORT": db_port,
        }

    database_url = os.getenv("DATABASE_URL")
    if database_url:
        try:
            return parse_database_url(database_url)
        except ValueError:
            pass

    return {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": db_name or "venus_luna",
        "USER": db_user or "postgres",
        "PASSWORD": db_password,
        "HOST": db_host or "127.0.0.1",
        "PORT": db_port,
    }


# --- BASE DE DONNÉES (PROD et fallback robuste) ---
if DEBUG:
    # LOCAL: PostgreSQL (fallback sur variables par défaut)
    DATABASES = {
        "default": get_database_config()
    }
else:
    # PROD: PostgreSQL via DATABASE_URL ou DB_*.
    DATABASES = {
        "default": get_database_config()
    }

# --- CONFIGURATION CLOUDINARY (avec fallback local) ---
try:
    import cloudinary
    import cloudinary.uploader
    import cloudinary.api
    cloudinary.config(
        cloud_name=os.getenv('CLOUDINARY_CLOUD_NAME', 'dse5hwjvt'),
        api_key=os.getenv('CLOUDINARY_API_KEY', '298756569597144'),
        api_secret=os.getenv('CLOUDINARY_API_SECRET', 'egry0kUkkucqSh7t7mR32zrElqA'),
        secure=True,
    )
    DEFAULT_FILE_STORAGE = 'cloudinary_storage.storage.MediaCloudinaryStorage'
except ImportError as e:
    print(f"Cloudinary non disponible: {e}. Utilisation stockage local.")
    DEFAULT_FILE_STORAGE = 'django.core.files.storage.FileSystemStorage'

# --- FICHIERS STATIQUES ET MEDIA ---
STATIC_URL = '/static/'
STATICFILES_DIRS = [BASE_DIR / 'static']
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'

MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

# --- INTERNATIONALISATION ---
LANGUAGE_CODE = 'fr-fr'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# --- AUTHENTIFICATION ---
LOGIN_URL = '/accounts/login/'
LOGIN_REDIRECT_URL = '/'

# --- BKAPAY (legacy) ---
BKAPAY_PUBLIC_KEY = os.getenv('BKAPAY_PUBLIC_KEY')
BKAPAY_SECRET_WEBHOOK = os.getenv('BKAPAY_SECRET_WEBHOOK')

# --- CASHPAY ---
# Utiliser la doc CashPay API v3 (OAuth2 + Link2Pay)
CASHPAY_CLIENT_ID = os.getenv('CASHPAY_CLIENT_ID')
CASHPAY_CLIENT_SECRET = os.getenv('CASHPAY_CLIENT_SECRET')
CASHPAY_USERNAME = os.getenv('CASHPAY_USERNAME')
CASHPAY_PASSWORD = os.getenv('CASHPAY_PASSWORD')

# Sandbox par défaut (à adapter si nécessaire)
CASHPAY_API_BASE_URL = os.getenv(
    'CASHPAY_API_BASE_URL',
    'https://api.semoa-payments.ovh/sandbox-v3'
)

# Clé/secret utilisé pour signer/décoder le JWT reçu en webhook.
# (Si CashPay utilise la clé de merchant/API key côté serveur, renseigner ici)
CASHPAY_SECRET_WEBHOOK = os.getenv('CASHPAY_SECRET_WEBHOOK')


# --- CONFIGURATION EMAIL (BREVO SMTP + FALLBACK) ---
EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = os.getenv('BREVO_SMTP_HOST', 'smtp-relay.brevo.com')
EMAIL_PORT = int(os.getenv('BREVO_SMTP_PORT', '587'))
EMAIL_USE_TLS = os.getenv('BREVO_SMTP_TLS', 'True').strip().lower() in {'1', 'true', 'yes', 'on'}
EMAIL_USE_SSL = os.getenv('BREVO_SMTP_SSL', 'False').strip().lower() in {'1', 'true', 'yes', 'on'}
EMAIL_TIMEOUT = int(os.getenv('EMAIL_TIMEOUT', '20'))

# Compatibilité descendante avec les anciennes variables EMAIL_* déjà utilisées.
EMAIL_HOST_USER = os.getenv('BREVO_SMTP_LOGIN') or os.getenv('EMAIL_HOST_USER') or os.getenv('EMAIL_USER')
EMAIL_HOST_PASSWORD = os.getenv('BREVO_SMTP_KEY') or os.getenv('EMAIL_HOST_PASSWORD') or os.getenv('EMAIL_APP_PASSWORD')

BREVO_FROM_EMAIL = os.getenv('BREVO_FROM_EMAIL', 'noreply@venus-luna.com')
DEFAULT_FROM_EMAIL = os.getenv('DEFAULT_FROM_EMAIL', f'Boutique Venus-Luna <{BREVO_FROM_EMAIL}>')
SERVER_EMAIL = os.getenv('SERVER_EMAIL', DEFAULT_FROM_EMAIL)

# Sécurité token reset mot de passe (24h)
PASSWORD_RESET_TIMEOUT = int(os.getenv('PASSWORD_RESET_TIMEOUT', '86400'))

# --- LIENS RÉSEAUX SOCIAUX ---
WHATSAPP_NUMBER = os.getenv('WHATSAPP_NUMBER', '22893343403')
FACEBOOK_URL = os.getenv('FACEBOOK_URL', 'https://www.facebook.com/venustogo')
TWITTER_URL = os.getenv('TWITTER_URL', 'https://twitter.com/venustogo')
INSTAGRAM_URL = os.getenv('INSTAGRAM_URL', 'https://www.instagram.com/venustogo/')
LINKEDIN_URL = os.getenv('LINKEDIN_URL', 'https://www.linkedin.com/company/venustogo/')
TIKTOK_URL = os.getenv('TIKTOK_URL', 'https://www.tiktok.com/@venustogo')
YOUTUBE_URL = os.getenv('YOUTUBE_URL', 'https://www.youtube.com/channel/venustogo')
