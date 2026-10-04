from pathlib import Path
from decouple import config
from datetime import timedelta
from email.utils import formataddr

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = config('SECRET_KEY')
DEBUG = config('DEBUG', default=False, cast=bool)
ALLOWED_HOSTS = config('ALLOWED_HOSTS', default='localhost').split(',')

# ─── Applications ─────────────────────────────────────────────────────────────
DJANGO_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
]
THIRD_PARTY_APPS = [
    'rest_framework',
    'rest_framework_simplejwt',
    'rest_framework_simplejwt.token_blacklist',
    'corsheaders',
    'drf_spectacular',
    'django_filters',
]
LOCAL_APPS = [
    'apps.accounts',
    'apps.equipements',
    'apps.alertes',
]
INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

# ─── Middleware ────────────────────────────────────────────────────────────────
MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'core.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
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

WSGI_APPLICATION = 'core.wsgi.application'

# ─── Base de données PostgreSQL ───────────────────────────────────────────────
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME':     config('DB_NAME',     default='smartfactory_db'),
        'USER':     config('DB_USER',     default='postgres'),
        'PASSWORD': config('DB_PASSWORD', default='postgres'),
        'HOST':     config('DB_HOST',     default='localhost'),
        'PORT':     config('DB_PORT',     default='5432'),
    }
}

# ─── Modèle utilisateur personnalisé ─────────────────────────────────────────
AUTH_USER_MODEL = 'accounts.Utilisateur'

# ─── Hachage bcrypt ──────────────────────────────────────────────────────────
PASSWORD_HASHERS = [
    'django.contrib.auth.hashers.BCryptSHA256PasswordHasher',
    'django.contrib.auth.hashers.PBKDF2PasswordHasher',
    'django.contrib.auth.hashers.PBKDF2SHA1PasswordHasher',
    'django.contrib.auth.hashers.Argon2PasswordHasher',
]

# ─── Validation mots de passe ────────────────────────────────────────────────
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

# ─── Internationalisation ─────────────────────────────────────────────────────
LANGUAGE_CODE = 'fr-fr'
TIME_ZONE = 'Africa/Algiers'
USE_I18N = True
USE_TZ = True

# ─── Fichiers statiques & médias ─────────────────────────────────────────────
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

# ─── Module 4 — Inspection visuelle par IA ───────────────────────────────────
# Backend du service d'analyse (remplaçable : 'mock' par défaut).
VISION_AI_BACKEND = config('VISION_AI_BACKEND', default='mock')
# Taille maximale acceptée pour une image d'inspection (Mo).
INSPECTION_IMAGE_MAX_MB = config('INSPECTION_IMAGE_MAX_MB', default=5, cast=int)

# ─── Module 8 — Alertes & Notifications (UC-26 → UC-29) ──────────────────────
# Les seuils des alertes ne sont PAS stockés ici : ils restent ceux des
# capteurs (`Sensor.seuil_min` / `Sensor.seuil_max`, Module 3). Seule la
# *logique de gravité* est paramétrable, pour être modifiable sans code.
#
# Règle de niveau (UC-27, explicite et sans IA) — voir `apps/alertes/engine.py` :
#   CRITIQUE si ratio_plage_pct >= ALERTE_CRITIQUE_RATIO_PCT
#              ou depassement   >= ALERTE_CRITIQUE_DEPASSEMENT
#   MAJEURE   si ratio_plage_pct >= ALERTE_MAJEURE_RATIO_PCT
#              ou depassement   >= ALERTE_MAJEURE_DEPASSEMENT
#   MINEURE   sinon
# avec ratio_plage_pct = depassement / (seuil_max − seuil_min) × 100.
ALERTE_MAJEURE_RATIO_PCT = config('ALERTE_MAJEURE_RATIO_PCT', default=10.0, cast=float)
ALERTE_CRITIQUE_RATIO_PCT = config('ALERTE_CRITIQUE_RATIO_PCT', default=25.0, cast=float)
ALERTE_MAJEURE_DEPASSEMENT = config('ALERTE_MAJEURE_DEPASSEMENT', default=20.0, cast=float)
ALERTE_CRITIQUE_DEPASSEMENT = config('ALERTE_CRITIQUE_DEPASSEMENT', default=50.0, cast=float)

# Le retour à la normale clôt automatiquement les alertes ouvertes du capteur.
ALERTE_RESOLUTION_AUTO = config('ALERTE_RESOLUTION_AUTO', default=True, cast=bool)

# ─── Module 8 — Canaux de notification (UC-28) ──────────────────────────────
# Les trois canaux sont désactivables sans toucher au code. Aucun canal ne doit
# jamais empêcher la création d'une alerte.
ALERTE_NOTIFICATIONS_IN_APP = config('ALERTE_NOTIFICATIONS_IN_APP', default=True, cast=bool)
ALERTE_NOTIFICATIONS_EMAIL = config('ALERTE_NOTIFICATIONS_EMAIL', default=False, cast=bool)
ALERTE_NOTIFICATIONS_SMS = config('ALERTE_NOTIFICATIONS_SMS', default=False, cast=bool)
# Destinataires de repli (CSV d'emails) : ignorés si l'email est désactivé.
ALERTE_NOTIFY_EMAILS = config('ALERTE_NOTIFY_EMAILS', default='').split(',')
ALERTE_EMAIL_NIVEAU_MIN = config('ALERTE_EMAIL_NIVEAU_MIN', default='MAJEURE')

# Twilio : OPTIONNEL. Sans ces variables, aucun SMS n'est envoyé et aucune
# erreur n'est levée (l'architecture du canal SMS est déjà en place).
TWILIO_ACCOUNT_SID = config('TWILIO_ACCOUNT_SID', default='')
TWILIO_AUTH_TOKEN = config('TWILIO_AUTH_TOKEN', default='')

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# ─── CORS ────────────────────────────────────────────────────────────────────
CORS_ALLOWED_ORIGINS = config(
    'CORS_ALLOWED_ORIGINS',
    default='http://localhost:3000,http://localhost:8080,http://127.0.0.1:8080'
).split(',')
CORS_ALLOW_CREDENTIALS = True

# ─── Django REST Framework ────────────────────────────────────────────────────
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'rest_framework_simplejwt.authentication.JWTAuthentication',
    ),
    'DEFAULT_PERMISSION_CLASSES': (
        'rest_framework.permissions.IsAuthenticated',
    ),
    'DEFAULT_SCHEMA_CLASS': 'drf_spectacular.openapi.AutoSchema',
    'DEFAULT_FILTER_BACKENDS': [
        'django_filters.rest_framework.DjangoFilterBackend',
        'rest_framework.filters.SearchFilter',
        'rest_framework.filters.OrderingFilter',
    ],
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 20,
    'DEFAULT_THROTTLE_CLASSES': [
        'rest_framework.throttling.AnonRateThrottle',
        'rest_framework.throttling.UserRateThrottle',
    ],
    'DEFAULT_THROTTLE_RATES': {
        'anon': '100/hour',
        'user': '1000/hour',
        'login': '5/min',
        'password_reset': '3/hour',
    },
}

# ─── JWT ─────────────────────────────────────────────────────────────────────
SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME':  timedelta(minutes=config('ACCESS_TOKEN_LIFETIME_MINUTES', default=15, cast=int)),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=config('REFRESH_TOKEN_LIFETIME_DAYS', default=7, cast=int)),
    'ROTATE_REFRESH_TOKENS':  True,
    'BLACKLIST_AFTER_ROTATION': True,
    'UPDATE_LAST_LOGIN': True,
    'AUTH_HEADER_TYPES': ('Bearer',),
    'USER_ID_FIELD': 'id',
    'USER_ID_CLAIM': 'user_id',
    'TOKEN_TYPE_CLAIM': 'token_type',
}

# ─── Swagger / OpenAPI ────────────────────────────────────────────────────────
SPECTACULAR_SETTINGS = {
    'TITLE': 'SmartFactory Twin API',
    'DESCRIPTION': 'API de maintenance prédictive industrielle — Module Authentification (Sprint 1)',
    'VERSION': '1.0.0',
    'SERVE_INCLUDE_SCHEMA': False,
    'COMPONENT_SPLIT_REQUEST': True,
    'SECURITY': [{'BearerAuth': []}],
    'COMPONENTS': {
        'securitySchemes': {
            'BearerAuth': {
                'type': 'http',
                'scheme': 'bearer',
                'bearerFormat': 'JWT',
            }
        }
    },
}

# ─── Email ───────────────────────────────────────────────────────────────────
EMAIL_BACKEND = config('EMAIL_BACKEND', default='django.core.mail.backends.console.EmailBackend')
EMAIL_HOST = config('EMAIL_HOST', default='localhost')
EMAIL_PORT = config('EMAIL_PORT', default=587, cast=int)
EMAIL_USE_TLS = config('EMAIL_USE_TLS', default=True, cast=bool)
EMAIL_HOST_USER = config('EMAIL_HOST_USER', default='')
EMAIL_HOST_PASSWORD = config('EMAIL_HOST_PASSWORD', default='')
EMAIL_DISPLAY_NAME = config('EMAIL_DISPLAY_NAME', default='SmartFactory Twin')
DEFAULT_FROM_EMAIL = formataddr((EMAIL_DISPLAY_NAME, config('DEFAULT_FROM_EMAIL', default='smartfactory@localhost')))

# ─── Frontend URL (liens de réinitialisation) ─────────────────────────────────
FRONTEND_URL = config('FRONTEND_URL', default='http://localhost:3000')

# ─── Logo base64 pour les emails ─────────────────────────────────────────────
import base64 as _b64, os as _os
_logo_candidates = [
    _os.path.join(BASE_DIR, 'staticfiles', 'logoSmart.png'),
    _os.path.join(BASE_DIR, 'staticfiles', 'logo_b64.txt'),
    _os.path.join(BASE_DIR, '.logo_b64.txt'),
    _os.path.join(BASE_DIR.parent, 'Smartfactory-frontend', 'src', 'assets', 'logoSmart.png'),
]
EMAIL_LOGO_B64 = ''
for _p in _logo_candidates:
    if _os.path.exists(_p):
        if _p.endswith('.txt'):
            try:
                with open(_p, 'r', encoding='utf-8') as _f:
                    EMAIL_LOGO_B64 = _f.read().strip()
                if EMAIL_LOGO_B64:
                    break
            except Exception:
                pass
        else:
            try:
                from PIL import Image as _Img
                import io as _io
                _img = _Img.open(_p).convert('RGBA')
                _img = _img.resize((80, 80), _Img.LANCZOS)
                _buf = _io.BytesIO()
                _img.save(_buf, format='PNG', optimize=True)
                EMAIL_LOGO_B64 = _b64.b64encode(_buf.getvalue()).decode()
                if EMAIL_LOGO_B64:
                    break
            except Exception:
                try:
                    with open(_p, 'rb') as _f:
                        EMAIL_LOGO_B64 = _b64.b64encode(_f.read()).decode()
                    if EMAIL_LOGO_B64:
                        break
                except Exception:
                    pass


# ─── Réinitialisation de mot de passe ────────────────────────────────────────
# Durée de validité du token de réinitialisation : 1 heure (3600 secondes)
PASSWORD_RESET_TIMEOUT = 3600

# ─── Démo superuser ──────────────────────────────────────────────────────────
DEMO_ADMIN_EMAIL = config('DEMO_ADMIN_EMAIL', default='admin@smartfactory.dz')
DEMO_ADMIN_PASSWORD = config('DEMO_ADMIN_PASSWORD', default='Admin@2024!')
