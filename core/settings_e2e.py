"""Isolated SQLite settings for real browser-to-API E2E checks.

The runner must provide a database file under the OS temporary directory whose
parent includes ``smartfactory-e2e-``. This prevents accidental use of a project
or production database.
"""
import os
import tempfile
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured

from .settings_test_runtime import *  # noqa: F403

_temp_root = Path(tempfile.gettempdir()).resolve()
_db_path = Path(os.environ.get('E2E_DB_PATH', '')).resolve()
if (_temp_root not in _db_path.parents
        or not any('smartfactory-e2e-' in part.lower() for part in _db_path.parts)):
    raise ImproperlyConfigured('E2E_DB_PATH must be inside a dedicated smartfactory-e2e-* temp directory.')

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': str(_db_path),
    }
}
ALLOWED_HOSTS = ['localhost', '127.0.0.1', 'testserver', 'host.docker.internal']
