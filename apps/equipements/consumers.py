from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import AccessToken

from .models import Sensor
from .permissions import accessible_machine_ids


class ReadingConsumer(AsyncJsonWebsocketConsumer):
    """Flux d'un capteur, authentifié par le JWT d'accès en query string."""

    async def connect(self):
        self.sensor_id = self.scope['url_route']['kwargs']['sensor_id']
        token = self.scope['query_string'].decode().split('token=', 1)[-1].split('&', 1)[0]
        self.user = await self._user_from_token(token)
        if not self.user or not await self._can_read_sensor():
            await self.close(code=4403)
            return

        self.group_name = f'reading_sensor_{self.sensor_id}'
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        if hasattr(self, 'group_name'):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def reading_update(self, event):
        await self.send_json(event['reading'])

    @database_sync_to_async
    def _user_from_token(self, raw_token):
        from apps.accounts.models import Utilisateur
        try:
            token = AccessToken(raw_token)
            return Utilisateur.objects.get(pk=token['user_id'], actif=True)
        except (TokenError, KeyError, Utilisateur.DoesNotExist):
            return None

    @database_sync_to_async
    def _can_read_sensor(self):
        return Sensor.objects.filter(
            pk=self.sensor_id, machine_id__in=accessible_machine_ids(self.user)
        ).exists()
