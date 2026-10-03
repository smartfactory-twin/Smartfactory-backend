from .settings import *  # noqa

# ─── Base de données SQLite en mémoire pour les tests ──────────────────────
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db_test.sqlite3',
    }
}

# ─── Email en mémoire pour inspecter mail.outbox dans les tests ───────────
EMAIL_BACKEND = 'django.core.mail.backends.locmem.EmailBackend'

# ─── Durée de validité du token de réinitialisation (1 heure) ─────────────
PASSWORD_RESET_TIMEOUT = 3600
