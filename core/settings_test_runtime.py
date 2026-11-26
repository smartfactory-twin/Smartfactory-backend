"""Temporary local test settings avoiding Daphne's sandbox-blocked socketpair."""
from .settings_test import *

INSTALLED_APPS = [app for app in INSTALLED_APPS if app != 'daphne']
