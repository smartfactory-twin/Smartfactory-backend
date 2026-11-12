from django.urls import path

from .consumers import ReadingConsumer

websocket_urlpatterns = [
    path('ws/readings/<int:sensor_id>/', ReadingConsumer.as_asgi()),
]
