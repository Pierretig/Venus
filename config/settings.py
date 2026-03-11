import os
from pathlib import Path
from dotenv import load_dotenv
import sys

# Chargement du fichier .env
load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, os.path.join(BASE_DIR, 'apps'))

# --- SITE ID pour Django Sites (SEO) ---
SITE_ID = 1

# --- SÉCURITÉ (Utilise les variables d'environnement / .env en local) ---
SECRET_KEY = os.getenv('SECRET_KEY', 'django-insecure-default-key-change-it')
DEBUG = os.getenv('DEBUG', 'False') == 'True'

ALLOWED_HOSTS_ENV = os.getenv('ALLOWED_HOSTS') or os.getenv('DJANGO_ALLOWED_HOSTS')
if ALLOWED_HOSTS_ENV:
    ALLOWED_HOSTS = [h.strip() for h in ALLOWED_HOSTS_ENV.split(',') if h.strip()]
else:
    ALLOWED_HOSTS = ['127.0.0.1', 'localhost']

# --- CORRECTION CSRF PRODUCTION ---
CSRF_TRUSTED_ORIGINS = [
    "https://venus-luna.com",
    "https://www.venus-luna.com"
]

SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

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
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'

# --- BASE DE DONNÉES (POSTGRESQL) ---
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.getenv('DB_NAME', 'venus-luna'),
        "USER": os.getenv('DB_USER', 'postgres'),
        "PASSWORD": os.getenv('DB_PASSWORD', 'Venus-luna@82'),
        "HOST": os.getenv('DB_HOST', 'venusluna-venus-data-base-mylun9'),
        "PORT": os.getenv('DB_PORT', '5432'),
    }
}
# DATABASES = {
#     "default": {
#         "ENGINE": "django.db.backends.postgresql",
#         "NAME": os.getenv('DB_NAME', 'venus_luna'),
#         "USER": os.getenv('DB_USER', 'postgres'),
#         "PASSWORD":  os.getenv('DB_PASSWORD', 'Peter@inos1'),
#         "HOST": os.getenv('DB_HOST', '127.0.0.1'),
#         "PORT": os.getenv('DB_PORT', '5432'),
#     }
# }

# --- CONFIGURATION CLOUDINARY ---
import cloudinary
cloudinary.config(
    cloud_name=os.getenv('CLOUDINARY_CLOUD_NAME', 'deidiffu8'),
    api_key=os.getenv('CLOUDINARY_API_KEY', '326153799291914'),
    api_secret=os.getenv('CLOUDINARY_API_SECRET', '8bmdZi4AoL937BAx_vrR5mi27U0'),
    secure=True,
)

# Stockage par défaut pour les fichiers uploadés (tous les champs ImageField)
DEFAULT_FILE_STORAGE = 'cloudinary_storage.storage.MediaCloudinaryStorage'

CLOUDINARY_STORAGE = {
    'CLOUD_NAME': os.getenv('CLOUDINARY_CLOUD_NAME', 'deidiffu8'),
    'API_KEY': os.getenv('CLOUDINARY_API_KEY', '326153799291914'),
    'API_SECRET': os.getenv('CLOUDINARY_API_SECRET', '8bmdZi4AoL937BAx_vrR5mi27U0'),
    'SECURE': True,
}

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

# --- BKAPAY ---
BKAPAY_PUBLIC_KEY = os.getenv('BKAPAY_PUBLIC_KEY')
BKAPAY_SECRET_WEBHOOK = os.getenv('BKAPAY_SECRET_WEBHOOK')

# --- CONFIGURATION EMAIL (GMAIL) ---
EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = 'smtp.gmail.com'
EMAIL_PORT = 587
EMAIL_USE_TLS = True
EMAIL_HOST_USER = os.getenv('EMAIL_USER')
EMAIL_HOST_PASSWORD = os.getenv('EMAIL_APP_PASSWORD')
DEFAULT_FROM_EMAIL = f'Venus Luna <{os.getenv("EMAIL_USER")}>'

# --- LIENS RÉSEAUX SOCIAUX ---
WHATSAPP_NUMBER = os.getenv('WHATSAPP_NUMBER', '22893343403')
FACEBOOK_URL = os.getenv('FACEBOOK_URL', 'https://www.facebook.com/venustogo')
TWITTER_URL = os.getenv('TWITTER_URL', 'https://twitter.com/venustogo')
INSTAGRAM_URL = os.getenv('INSTAGRAM_URL', 'https://www.instagram.com/venustogo/')
LINKEDIN_URL = os.getenv('LINKEDIN_URL', 'https://www.linkedin.com/company/venustogo/')
TIKTOK_URL = os.getenv('TIKTOK_URL', 'https://www.tiktok.com/@venustogo')