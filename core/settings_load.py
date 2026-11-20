"""Load-test profile. Never use it for a public or production deployment."""
from .settings import *  # noqa: F401,F403

REST_FRAMEWORK['DEFAULT_THROTTLE_RATES'] = {
    'anon': '100000/hour',
    'user': '100000/hour',
    'login': '10000/min',
    'password_reset': '1000/hour',
}
