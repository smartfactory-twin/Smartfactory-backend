"""Acceptance checks for the authenticated Sprint 3 reading stream."""
from asgiref.sync import async_to_sync
from channels.db import database_sync_to_async
from channels.testing import WebsocketCommunicator
import pytest
from django.utils import timezone
from rest_framework_simplejwt.tokens import AccessToken

from apps.accounts.models import Utilisateur
from apps.equipements.models import (
    LigneProduction, Machine, Reading, Sensor, Usine, UserScope, Zone,
)
from core.asgi import application


@pytest.fixture
def machine(db):
    usine = Usine.objects.create(nom='Usine WS')
    zone = Zone.objects.create(nom='Zone WS', usine=usine)
    ligne = LigneProduction.objects.create(nom='Ligne WS', zone=zone)
    return Machine.objects.create(
        nom='Machine WS', identifiant_interne='WS-001', ligne_production=ligne,
    )


@pytest.fixture
def sensor(db, machine):
    return Sensor.objects.create(
        identifiant='WS-TEMP-001', nom='Température WS',
        type_capteur='TEMPERATURE', machine=machine, unite='°C',
        frequence_mesure=10, seuil_min=0, seuil_max=100,
    )


@pytest.fixture
def admin_user(db):
    return Utilisateur.objects.create_user(
        email='ws-admin@smartfactory.test', password='Admin@123!', role='ADMIN',
        nom='Admin', prenom='WS',
    )


@pytest.mark.django_db(transaction=True)
def test_authenticated_client_receives_new_sensor_reading(sensor, admin_user):
    token = str(AccessToken.for_user(admin_user))

    async def exercise_stream():
        communicator = WebsocketCommunicator(
            application, f'/ws/readings/{sensor.id}/?token={token}',
            headers=[(b'origin', b'http://localhost')],
        )
        connected, _ = await communicator.connect()
        assert connected

        await database_sync_to_async(Reading.objects.create)(
            sensor_id=sensor.id, valeur=42.5, timestamp=timezone.now(),
        )
        payload = await communicator.receive_json_from(timeout=2)
        assert payload['sensor'] == sensor.id
        assert payload['valeur'] == 42.5
        assert payload['hors_plage'] is False
        await communicator.disconnect()

    async_to_sync(exercise_stream)()


@pytest.mark.django_db(transaction=True)
def test_invalid_jwt_is_rejected(sensor):
    async def exercise_rejection():
        communicator = WebsocketCommunicator(
            application, f'/ws/readings/{sensor.id}/?token=invalid',
            headers=[(b'origin', b'http://localhost')],
        )
        connected, details = await communicator.connect()
        assert not connected
        assert details == 4403

    async_to_sync(exercise_rejection)()


@pytest.mark.django_db(transaction=True)
def test_non_admin_without_sensor_scope_is_rejected(sensor):
    tech = Utilisateur.objects.create_user(
        email='ws-tech@smartfactory.test', password='Tech@123!', role='TECHNICIEN',
        nom='Technicien', prenom='WS',
    )
    token = str(AccessToken.for_user(tech))

    async def exercise_rejection():
        communicator = WebsocketCommunicator(
            application, f'/ws/readings/{sensor.id}/?token={token}',
            headers=[(b'origin', b'http://localhost')],
        )
        connected, details = await communicator.connect()
        assert not connected
        assert details == 4403

    async_to_sync(exercise_rejection)()


@pytest.mark.django_db(transaction=True)
def test_scoped_technician_can_subscribe_to_assigned_sensor(sensor, machine):
    usine = machine.ligne_production.zone.usine
    tech = Utilisateur.objects.create_user(
        email='ws-tech-scoped@smartfactory.test', password='Tech@123!', role='TECHNICIEN',
        nom='Technicien', prenom='WS',
    )
    UserScope.objects.create(utilisateur=tech, usine=usine)
    token = str(AccessToken.for_user(tech))

    async def exercise_access():
        communicator = WebsocketCommunicator(
            application, f'/ws/readings/{sensor.id}/?token={token}',
            headers=[(b'origin', b'http://localhost')],
        )
        connected, _ = await communicator.connect()
        assert connected
        await communicator.disconnect()

    async_to_sync(exercise_access)()
