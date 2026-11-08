"""
ASGI config — adds WebSocket support via Django Channels.
Replace your existing core/asgi.py with this.
"""
import os
from django.core.asgi import get_asgi_application
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.auth import AuthMiddlewareStack

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "core.settings")

# Import websocket patterns from each app
from apps.equipements.routing import websocket_urlpatterns as equipment_ws

application = ProtocolTypeRouter({
    "http": get_asgi_application(),
    "websocket": AuthMiddlewareStack(
        URLRouter(equipment_ws)
    ),
})
