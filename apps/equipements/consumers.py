import json
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.utils import timezone
import asyncio


class ReadingsConsumer(AsyncWebsocketConsumer):
    """
    UC-13 — WebSocket consumer for real-time sensor readings.
    URL: ws/machines/<machine_id>/readings/

    Protocol:
      Client → Server: { "action": "subscribe", "sensors": ["temp", "vib"] }
      Server → Client: { "sensor_id": "temp", "timestamp": 1699..., "value": 72.3 }
      Server → Client: { "type": "ping" }  (keepalive every 30s)
    """

    async def connect(self):
        self.machine_id = self.scope["url_route"]["kwargs"]["machine_id"]
        self.group_name = f"machine_{self.machine_id}_readings"
        self.subscribed_sensors = None  # None = all sensors
        self.ping_task = None

        # Check authentication
        user = self.scope.get("user")
        if not user or not user.is_authenticated:
            await self.close(code=4001)
            return

        # Join group
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

        # Start ping keepalive
        self.ping_task = asyncio.ensure_future(self._ping_loop())

    async def disconnect(self, code):
        if self.ping_task:
            self.ping_task.cancel()
        await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def receive(self, text_data=None, bytes_data=None):
        """Handle client messages."""
        try:
            data = json.loads(text_data or "{}")
        except json.JSONDecodeError:
            return

        action = data.get("action")
        if action == "subscribe":
            self.subscribed_sensors = data.get("sensors")  # list or None
        elif action == "ping":
            await self.send(json.dumps({"type": "pong"}))

    # ── Group message handler ──────────────────────────────────────
    async def sensor_reading(self, event):
        """
        Called when a reading is broadcast to the group.
        event: { "type": "sensor_reading", "sensor_id": str, "timestamp": int, "value": float }
        """
        # Filter by subscribed sensors if set
        if self.subscribed_sensors and event["sensor_id"] not in self.subscribed_sensors:
            return
        await self.send(json.dumps({
            "sensor_id": event["sensor_id"],
            "timestamp":  event["timestamp"],
            "value":      event["value"],
        }))

    # ── Keepalive ──────────────────────────────────────────────────
    async def _ping_loop(self):
        while True:
            await asyncio.sleep(30)
            try:
                await self.send(json.dumps({"type": "ping"}))
            except Exception:
                break
