"""
UC-13 — WebSocket routing for sensor readings.
Add this to your project-level routing.py
"""
from django.urls import re_path
from . import consumers

websocket_urlpatterns = [
    re_path(
        r"^ws/machines/(?P<machine_id>[^/]+)/readings/$",
        consumers.ReadingsConsumer.as_asgi(),
    ),
]
