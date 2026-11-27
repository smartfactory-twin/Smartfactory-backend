"""Temporary local test settings avoiding Daphne's sandbox-blocked socketpair."""
from .settings_test import *

INSTALLED_APPS = [app for app in INSTALLED_APPS if app != 'daphne']

# APIClient tests also send requests with SERVER_NAME=127.0.0.1.
ALLOWED_HOSTS = ['testserver', 'localhost', '127.0.0.1']
