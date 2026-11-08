"""
UC-13 — Broadcast a new sensor reading to WebSocket subscribers.
Called from ReadingCreateView after saving a new reading.
"""
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync


def broadcast_reading(machine_id: str, sensor_id: str, timestamp_ms: int, value: float):
    """
    Push a reading to the channel group for the given machine.
    Safe to call from synchronous Django views / Celery tasks.
    """
    channel_layer = get_channel_layer()
    if channel_layer is None:
        return  # channels not configured (e.g. tests)

    group_name = f"machine_{machine_id}_readings"
    async_to_sync(channel_layer.group_send)(
        group_name,
        {
            "type":      "sensor_reading",   # maps to consumer method name
            "sensor_id": str(sensor_id),
            "timestamp": timestamp_ms,
            "value":     float(value),
        },
    )
