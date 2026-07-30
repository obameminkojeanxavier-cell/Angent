import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.getenv('SECRET_KEY', 'django-insecure-change-this-in-production')

DEBUG = os.getenv('DEBUG', 'False') == 'True'

ALLOWED_HOSTS = os.getenv('ALLOWED_HOSTS', 'localhost,127.0.0.1').split(',')

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'rest_framework',
    'api',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'api.rate_limit.RateLimitMiddleware',
    'api.orchestration.OrchestrationMiddleware',
]

ROOT_URLCONF = 'datahub.urls'

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
            ],
        },
    },
]

WSGI_APPLICATION = 'datahub.wsgi.application'

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': os.getenv('DB_NAME', 'datahub'),
        'USER': os.getenv('DB_USER', 'datahub_user'),
        'PASSWORD': os.getenv('DB_PASSWORD', ''),
        'HOST': os.getenv('DB_HOST', 'localhost'),
        'PORT': os.getenv('DB_PORT', '5432'),
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LANGUAGE_CODE = 'fr-fr'
TIME_ZONE = 'Europe/Paris'
USE_I18N = True
USE_TZ = True

STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# API Configuration
# Token maître (compte "master", tous scopes). Les autres agents ont leurs
# propres tokens créés via `manage.py create_agent`.
API_TOKEN = os.getenv('API_TOKEN', '')

# Si True, la lecture des données exige aussi un token (scope data:read).
# Si False (défaut), la lecture reste publique pour la page de consultation
# (protégée par Cloudflare Access), et le scope n'est vérifié que si un token
# est fourni.
REQUIRE_AUTH_FOR_READ = os.getenv('REQUIRE_AUTH_FOR_READ', 'False') == 'True'

# Autorise la console web (interface GOD HAND) à exécuter des documents sans
# token, en tant que compte master. En local (DEBUG) : activé par défaut.
# En production : désactivé par défaut (protéger le site par Cloudflare Access,
# puis mettre ALLOW_WEB_CONSOLE=True, ou fournir un token skills:trigger).
ALLOW_WEB_CONSOLE = os.getenv('ALLOW_WEB_CONSOLE', 'True' if DEBUG else 'False') == 'True'

# URL de base annoncée dans le schéma OpenAPI (/openapi.json) pour les GPT
# Actions. Vide = déduite de la requête (scheme + host).
OPENAPI_BASE_URL = os.getenv('OPENAPI_BASE_URL', '')

# REST Framework
REST_FRAMEWORK = {
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
    'DEFAULT_AUTHENTICATION_CLASSES': [],
}

# Derrière Cloudflare Tunnel + Apache, la requête arrive en HTTP sur l'origine ;
# le protocole d'origine (https) est transmis via X-Forwarded-Proto. Sans ceci,
# SECURE_SSL_REDIRECT provoquerait une boucle de redirection infinie.
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
USE_X_FORWARDED_HOST = True

# CSRF : autoriser explicitement l'origine publique (Django 4+ l'exige pour les
# requêtes POST non-API via formulaire ; sans effet sur l'API à token).
CSRF_TRUSTED_ORIGINS = [
    'https://' + h for h in ALLOWED_HOSTS if h not in ('localhost', '127.0.0.1')
]

# Security settings for production
if not DEBUG:
    SECURE_SSL_REDIRECT = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_BROWSER_XSS_FILTER = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
    X_FRAME_OPTIONS = 'DENY'

# Rate limiting configuration
RATE_LIMIT_PER_MINUTE = int(os.getenv('RATE_LIMIT_PER_MINUTE', '60'))
RATE_LIMIT_PER_HOUR = int(os.getenv('RATE_LIMIT_PER_HOUR', '1000'))

# Orchestration middleware : routes exemptées de la vérification de l'orchestrateur
ORCHESTRATION_EXEMPT_PATHS = [
    '/manage/',
    '/admin/',
    '/api.md',
    '/skill.md',
    '/openapi.json',
    '/a/',
    '/static/',
    '/console/',
    '/api/skills/orchestrator/active/',  # Endpoint dédié exempté
    '/api/skills/',  # Endpoint de liste des skills exempté
]
