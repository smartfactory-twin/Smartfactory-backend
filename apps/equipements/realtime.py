from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer


def on_reading_created(sender, instance, created, raw=False, **kwargs):
    """Publie les nouvelles mesures créées, sans diffuser les fixtures brutes."""
    if created and not raw:
        publish_reading(instance)


def publish_reading(reading):
    """Diffuse une nouvelle mesure aux clients autorisés abonnés au capteur."""
    channel_layer = get_channel_layer()
    if channel_layer is None:
        return
    sensor = reading.sensor
    async_to_sync(channel_layer.group_send)(
        f'reading_sensor_{sensor.pk}',
        {
            'type': 'reading.update',
            'reading': {
                'id': reading.pk,
                'sensor': sensor.pk,
                'sensor_identifiant': sensor.identifiant,
                'valeur': reading.valeur,
                'timestamp': reading.timestamp.isoformat(),
                'hors_plage': reading.hors_plage,
                'est_valide': reading.est_valide,
                'interpolation': reading.interpolation,
            },
        },
    )
