"""Tests Module 3 — Capteurs & Données IoT (UC-08, UC-09, UC-10)."""
import csv
import io
from datetime import datetime, timezone as dt_timezone

import pytest
from rest_framework.test import APIClient

from apps.accounts.models import Utilisateur
from apps.equipements.models import (
    Usine, Zone, LigneProduction, Machine, Sensor, Reading,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def admin_user(db):
    return Utilisateur.objects.create_user(
        email='m3-admin@smartfactory.com', password='Admin@123!', role='ADMIN',
        nom='Admin', prenom='Module3'
    )


@pytest.fixture
def tech_user(db):
    return Utilisateur.objects.create_user(
        email='m3-tech@smartfactory.com', password='Tech@123!', role='TECHNICIEN',
        nom='Tech', prenom='Module3'
    )


@pytest.fixture
def op_user(db):
    return Utilisateur.objects.create_user(
        email='m3-op@smartfactory.com', password='Op@123!', role='OPERATEUR',
        nom='Op', prenom='Module3'
    )


@pytest.fixture
def machine(db):
    usine = Usine.objects.create(nom='Usine M3')
    zone = Zone.objects.create(nom='Zone M3', usine=usine)
    ligne = LigneProduction.objects.create(nom='Ligne M3', zone=zone)
    return Machine.objects.create(
        nom='Tour CNC TC-004', identifiant_interne='TC-004',
        statut='NORMAL', ligne_production=ligne,
    )


@pytest.fixture
def sensor(db, machine):
    return Sensor.objects.create(
        identifiant='TEMP-001', nom='Temperature Sensor 01',
        type_capteur='TEMPERATURE', machine=machine,
        unite='°C', frequence_mesure=10, seuil_min=0, seuil_max=80,
    )


def make_readings_csv(rows, fieldnames=('sensor_id', 'timestamp', 'value')):
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()
    for row in rows:
        writer.writerow(row)
    output.seek(0)
    file_bytes = io.BytesIO(output.read().encode('utf-8'))
    file_bytes.name = 'readings_test.csv'
    return file_bytes


SENSOR_PAYLOAD = {
    'identifiant': 'TEMP-002',
    'nom': 'Temperature Sensor 02',
    'type_capteur': 'TEMPERATURE',
    'unite': '°C',
    'frequence_mesure': 10,
    'seuil_min': 0,
    'seuil_max': 80,
}


# ── UC-08 : création / validation des capteurs ────────────────────────────────

@pytest.mark.django_db
class TestSensorCreate:
    def test_01_create_sensor(self, api_client, admin_user, machine):
        api_client.force_authenticate(admin_user)
        payload = {**SENSOR_PAYLOAD, 'machine': machine.id}
        r = api_client.post('/api/equipements/capteurs/', payload)
        assert r.status_code == 201
        assert Sensor.objects.filter(identifiant='TEMP-002').exists()
        assert r.data['machine_identifiant'] == 'TC-004'

    def test_02_create_sensor_invalid_machine(self, api_client, admin_user):
        api_client.force_authenticate(admin_user)
        payload = {**SENSOR_PAYLOAD, 'machine': 999999}
        r = api_client.post('/api/equipements/capteurs/', payload)
        assert r.status_code == 400
        assert not Sensor.objects.filter(identifiant='TEMP-002').exists()

    def test_03_duplicate_identifier(self, api_client, admin_user, machine, sensor):
        api_client.force_authenticate(admin_user)
        payload = {**SENSOR_PAYLOAD, 'identifiant': 'TEMP-001', 'machine': machine.id}
        r = api_client.post('/api/equipements/capteurs/', payload)
        assert r.status_code == 400
        assert Sensor.objects.filter(identifiant='TEMP-001').count() == 1

    def test_04_invalid_sensor_type(self, api_client, admin_user, machine):
        api_client.force_authenticate(admin_user)
        payload = {**SENSOR_PAYLOAD, 'type_capteur': 'INCONNU', 'machine': machine.id}
        r = api_client.post('/api/equipements/capteurs/', payload)
        assert r.status_code == 400

    def test_05_invalid_thresholds(self, api_client, admin_user, machine):
        api_client.force_authenticate(admin_user)
        payload = {**SENSOR_PAYLOAD, 'seuil_min': 90, 'seuil_max': 10, 'machine': machine.id}
        r = api_client.post('/api/equipements/capteurs/', payload)
        assert r.status_code == 400

    def test_05b_invalid_frequency(self, api_client, admin_user, machine):
        api_client.force_authenticate(admin_user)
        payload = {**SENSOR_PAYLOAD, 'frequence_mesure': 0, 'machine': machine.id}
        r = api_client.post('/api/equipements/capteurs/', payload)
        assert r.status_code == 400


# ── UC-08 : mise à jour / suppression / lecture ───────────────────────────────

@pytest.mark.django_db
class TestSensorCRUD:
    def test_06_update_sensor(self, api_client, admin_user, sensor):
        api_client.force_authenticate(admin_user)
        r = api_client.patch(f'/api/equipements/capteurs/{sensor.id}/', {
            'nom': 'Température modifiée', 'seuil_max': 95,
        })
        assert r.status_code == 200
        sensor.refresh_from_db()
        assert sensor.nom == 'Température modifiée'
        assert sensor.seuil_max == 95

    def test_06b_partial_update_keeps_validity(self, api_client, admin_user, sensor):
        # PATCH d'un seul seuil doit être validé contre la valeur existante.
        api_client.force_authenticate(admin_user)
        r = api_client.patch(f'/api/equipements/capteurs/{sensor.id}/', {'seuil_min': 200})
        assert r.status_code == 400

    def test_07_delete_sensor(self, api_client, admin_user, sensor):
        api_client.force_authenticate(admin_user)
        sensor_id = sensor.id
        r = api_client.delete(f'/api/equipements/capteurs/{sensor_id}/')
        assert r.status_code == 204
        assert not Sensor.objects.filter(id=sensor_id).exists()

    def test_08_list_sensors(self, api_client, admin_user, machine, sensor):
        Sensor.objects.create(
            identifiant='VIB-001', nom='Vibration 01', type_capteur='VIBRATION',
            machine=machine, unite='mm/s', frequence_mesure=5, seuil_min=0, seuil_max=50,
        )
        api_client.force_authenticate(admin_user)
        r = api_client.get('/api/equipements/capteurs/')
        assert r.status_code == 200
        assert r.data['count'] == 2

    def test_09_filter_by_machine(self, api_client, admin_user, machine, sensor):
        usine2 = Usine.objects.create(nom='Usine M3 bis')
        zone2 = Zone.objects.create(nom='Zone bis', usine=usine2)
        ligne2 = LigneProduction.objects.create(nom='Ligne bis', zone=zone2)
        machine2 = Machine.objects.create(
            nom='Autre machine', identifiant_interne='TC-999',
            statut='NORMAL', ligne_production=ligne2,
        )
        Sensor.objects.create(
            identifiant='TEMP-999', nom='Temp autre', type_capteur='TEMPERATURE',
            machine=machine2, unite='°C', frequence_mesure=10, seuil_min=0, seuil_max=90,
        )
        api_client.force_authenticate(admin_user)
        r = api_client.get(f'/api/equipements/capteurs/?machine={machine.id}')
        assert r.status_code == 200
        assert r.data['count'] == 1
        assert r.data['results'][0]['identifiant'] == 'TEMP-001'

    def test_10_filter_by_type(self, api_client, admin_user, machine, sensor):
        Sensor.objects.create(
            identifiant='VIB-001', nom='Vibration 01', type_capteur='VIBRATION',
            machine=machine, unite='mm/s', frequence_mesure=5, seuil_min=0, seuil_max=50,
        )
        api_client.force_authenticate(admin_user)
        r = api_client.get('/api/equipements/capteurs/?type_capteur=TEMPERATURE')
        assert r.status_code == 200
        assert r.data['count'] == 1
        assert r.data['results'][0]['type_capteur'] == 'TEMPERATURE'

    def test_10b_search(self, api_client, admin_user, sensor):
        api_client.force_authenticate(admin_user)
        r = api_client.get('/api/equipements/capteurs/?search=TEMP-001')
        assert r.status_code == 200
        assert r.data['count'] == 1

    def test_10c_filter_by_status(self, api_client, admin_user, machine, sensor):
        Sensor.objects.create(
            identifiant='VIB-002', nom='Vibration inactive', type_capteur='VIBRATION',
            machine=machine, unite='mm/s', frequence_mesure=5, seuil_min=0, seuil_max=50,
            actif=False,
        )
        api_client.force_authenticate(admin_user)
        r = api_client.get('/api/equipements/capteurs/?actif=true')
        assert r.status_code == 200
        assert r.data['count'] == 1
        assert r.data['results'][0]['identifiant'] == 'TEMP-001'

        r_inactifs = api_client.get('/api/equipements/capteurs/?actif=false')
        assert r_inactifs.status_code == 200
        assert r_inactifs.data['count'] == 1
        assert r_inactifs.data['results'][0]['identifiant'] == 'VIB-002'


# ── UC-09 : ingestion des mesures ─────────────────────────────────────────────

@pytest.mark.django_db
class TestReadingCreate:
    def test_11_create_reading(self, api_client, admin_user, sensor):
        api_client.force_authenticate(admin_user)
        r = api_client.post('/api/readings/', {
            'sensor': 'TEMP-001',
            'value': 72.5,
            'timestamp': '2026-10-03T10:30:00Z',
        }, format='json')
        assert r.status_code == 201
        assert Reading.objects.count() == 1
        reading = Reading.objects.first()
        assert reading.valeur == 72.5
        assert reading.sensor == sensor

    def test_11b_create_reading_with_pk(self, api_client, admin_user, sensor):
        api_client.force_authenticate(admin_user)
        r = api_client.post('/api/readings/', {
            'sensor': sensor.id, 'valeur': 60, 'timestamp': '2026-10-03T10:31:00Z',
        }, format='json')
        assert r.status_code == 201

    def test_12_invalid_reading_non_numeric(self, api_client, admin_user, sensor):
        api_client.force_authenticate(admin_user)
        r = api_client.post('/api/readings/', {
            'sensor': 'TEMP-001', 'value': 'abc', 'timestamp': '2026-10-03T10:30:00Z',
        }, format='json')
        assert r.status_code == 400
        assert Reading.objects.count() == 0

    def test_13_reading_unknown_sensor(self, api_client, admin_user):
        api_client.force_authenticate(admin_user)
        r = api_client.post('/api/readings/', {
            'sensor': 'NOPE-999', 'value': 10, 'timestamp': '2026-10-03T10:30:00Z',
        }, format='json')
        assert r.status_code == 400
        assert Reading.objects.count() == 0

    def test_14_invalid_timestamp(self, api_client, admin_user, sensor):
        api_client.force_authenticate(admin_user)
        r = api_client.post('/api/readings/', {
            'sensor': 'TEMP-001', 'value': 10, 'timestamp': 'pas-une-date',
        }, format='json')
        assert r.status_code == 400
        assert Reading.objects.count() == 0

    def test_15_out_of_range_value(self, api_client, admin_user, sensor):
        api_client.force_authenticate(admin_user)
        r = api_client.post('/api/readings/', {
            'sensor': 'TEMP-001', 'value': 100, 'timestamp': '2026-10-03T10:30:00Z',
        }, format='json')
        assert r.status_code == 201
        reading = Reading.objects.get()
        assert reading.hors_plage is True
        assert reading.est_valide is False
        # La donnée d'origine n'est jamais supprimée.
        assert reading.valeur == 100

    def test_16_utc_timestamp(self, api_client, admin_user, sensor):
        api_client.force_authenticate(admin_user)
        r = api_client.post('/api/readings/', {
            'sensor': 'TEMP-001', 'value': 50,
            'timestamp': '2026-10-03T12:30:00+02:00',
        }, format='json')
        assert r.status_code == 201
        reading = Reading.objects.get()
        assert reading.timestamp.tzinfo is not None
        assert reading.timestamp.astimezone(dt_timezone.utc).hour == 10


# ── UC-09 : import CSV / JSON ─────────────────────────────────────────────────

@pytest.mark.django_db
class TestReadingsImport:
    def test_17_csv_import(self, api_client, admin_user, sensor):
        api_client.force_authenticate(admin_user)
        f = make_readings_csv([
            {'sensor_id': 'TEMP-001', 'timestamp': '2026-10-03T10:00:00Z', 'value': '65.2'},
            {'sensor_id': 'TEMP-001', 'timestamp': '2026-10-03T10:01:00Z', 'value': '66.1'},
            {'sensor_id': 'TEMP-001', 'timestamp': '2026-10-03T10:02:00Z', 'value': '67.4'},
        ])
        r = api_client.post('/api/equipements/readings/import_csv/', {'file': f}, format='multipart')
        assert r.status_code == 200
        assert r.data['imported'] == 3
        assert r.data['rejected'] == 0
        assert Reading.objects.count() == 3

    def test_18_csv_invalid_row_reported(self, api_client, admin_user, sensor):
        api_client.force_authenticate(admin_user)
        f = make_readings_csv([
            {'sensor_id': 'TEMP-001', 'timestamp': '2026-10-03T10:00:00Z', 'value': '65.2'},
            {'sensor_id': 'TEMP-001', 'timestamp': 'invalid-ts', 'value': '66.1'},
            {'sensor_id': 'UNKNOWN', 'timestamp': '2026-10-03T10:02:00Z', 'value': '67.4'},
            {'sensor_id': 'TEMP-001', 'timestamp': '2026-10-03T10:03:00Z', 'value': 'abc'},
        ])
        r = api_client.post('/api/equipements/readings/import_csv/', {'file': f}, format='multipart')
        assert r.status_code == 200
        assert r.data['imported'] == 1
        assert r.data['rejected'] == 3
        assert len(r.data['errors']) == 3
        # Aucune perte silencieuse : les lignes valides sont bien créées.
        assert Reading.objects.count() == 1

    def test_18b_csv_duplicate_rows(self, api_client, admin_user, sensor):
        api_client.force_authenticate(admin_user)
        row = {'sensor_id': 'TEMP-001', 'timestamp': '2026-10-03T10:00:00Z', 'value': '65.2'}
        f = make_readings_csv([row, dict(row)])
        r = api_client.post('/api/equipements/readings/import_csv/', {'file': f}, format='multipart')
        assert r.status_code == 200
        assert r.data['imported'] == 1
        assert r.data['duplicates'] == 1

    def test_18c_csv_preview_does_not_insert(self, api_client, admin_user, sensor):
        api_client.force_authenticate(admin_user)
        f = make_readings_csv([
            {'sensor_id': 'TEMP-001', 'timestamp': '2026-10-03T10:00:00Z', 'value': '65.2'},
            {'sensor_id': 'TEMP-001', 'timestamp': 'invalid', 'value': '1'},
        ])
        r = api_client.post('/api/equipements/readings/preview_csv/', {'file': f}, format='multipart')
        assert r.status_code == 200
        assert r.data['imported'] == 1
        assert r.data['rejected'] == 1
        assert Reading.objects.count() == 0

    def test_19_json_import(self, api_client, admin_user, sensor):
        api_client.force_authenticate(admin_user)
        payload = [
            {'sensor_id': 'TEMP-001', 'timestamp': '2026-10-03T10:00:00Z', 'value': 65.2},
            {'sensor_id': 'TEMP-001', 'timestamp': '2026-10-03T10:01:00Z', 'value': 66.1},
        ]
        r = api_client.post('/api/equipements/readings/import_json/', payload, format='json')
        assert r.status_code == 200
        assert r.data['imported'] == 2
        assert Reading.objects.count() == 2

    def test_19b_json_invalid_payload(self, api_client, admin_user):
        api_client.force_authenticate(admin_user)
        r = api_client.post('/api/equipements/readings/import_json/', {'not': 'a list'}, format='json')
        assert r.status_code == 400

    def test_19c_json_preview_does_not_insert(self, api_client, admin_user, sensor):
        api_client.force_authenticate(admin_user)
        payload = [
            {'sensor_id': 'TEMP-001', 'timestamp': '2026-10-03T10:00:00Z', 'value': 65.2},
            {'sensor_id': 'NOPE-999', 'timestamp': '2026-10-03T10:01:00Z', 'value': 1},
        ]
        r = api_client.post('/api/equipements/readings/preview_json/', payload, format='json')
        assert r.status_code == 200
        assert r.data['imported'] == 1
        assert r.data['rejected'] == 1
        assert Reading.objects.count() == 0

    def test_csv_import_via_alias_route(self, api_client, admin_user, sensor):
        api_client.force_authenticate(admin_user)
        f = make_readings_csv([
            {'sensor_id': 'TEMP-001', 'timestamp': '2026-10-03T10:00:00Z', 'value': '42'},
        ])
        r = api_client.post('/api/readings/import_csv/', {'file': f}, format='multipart')
        assert r.status_code == 200
        assert r.data['imported'] == 1


# ── UC-10, RULE 2 : interpolation des petits trous ────────────────────────────

@pytest.mark.django_db
class TestPreprocessing:
    def test_interpolation_small_gap(self, api_client, admin_user, sensor):
        sensor.frequence_mesure = 60  # 1 minute
        sensor.save(update_fields=['frequence_mesure'])
        api_client.force_authenticate(admin_user)
        # Deux mesures espacées de 3 minutes (fréquence 1 min) → 2 points manquants.
        f = make_readings_csv([
            {'sensor_id': 'TEMP-001', 'timestamp': '2026-10-03T10:00:00Z', 'value': '10'},
            {'sensor_id': 'TEMP-001', 'timestamp': '2026-10-03T10:03:00Z', 'value': '40'},
        ])
        r = api_client.post('/api/equipements/readings/import_csv/', {'file': f}, format='multipart')
        assert r.status_code == 200
        assert r.data['imported'] == 2
        # UC-09 : l'ingestion n'invente rien.
        assert r.data['interpolated'] == 0
        assert Reading.objects.count() == 2

        # UC-10 : le prétraitement explicite interpole le petit trou.
        r2 = api_client.post('/api/readings/preprocess/', {'sensor': 'TEMP-001'}, format='json')
        assert r2.status_code == 200
        assert r2.data['interpolated'] == 2
        assert Reading.objects.filter(interpolation=True).count() == 2

    def test_no_interpolation_large_gap(self, api_client, admin_user, sensor):
        sensor.frequence_mesure = 60
        sensor.save(update_fields=['frequence_mesure'])
        api_client.force_authenticate(admin_user)
        # Deux mesures espacées de 10 minutes (>= 5 min) → aucune invention.
        f = make_readings_csv([
            {'sensor_id': 'TEMP-001', 'timestamp': '2026-10-03T10:00:00Z', 'value': '10'},
            {'sensor_id': 'TEMP-001', 'timestamp': '2026-10-03T10:10:00Z', 'value': '40'},
        ])
        r = api_client.post('/api/equipements/readings/import_csv/', {'file': f}, format='multipart')
        assert r.status_code == 200
        assert r.data['imported'] == 2

        r2 = api_client.post('/api/readings/preprocess/', {'sensor': 'TEMP-001'}, format='json')
        assert r2.status_code == 200
        assert r2.data['interpolated'] == 0
        assert Reading.objects.filter(interpolation=True).count() == 0

    def test_preprocess_marks_out_of_range(self, api_client, admin_user, sensor):
        api_client.force_authenticate(admin_user)
        # Lecture insérée directement (sans prétraitement).
        Reading.objects.create(
            sensor=sensor, valeur=150,
            timestamp=datetime(2026, 10, 3, 10, 0, tzinfo=dt_timezone.utc),
        )
        r = api_client.post('/api/readings/preprocess/', {'sensor': 'TEMP-001'}, format='json')
        assert r.status_code == 200
        assert r.data['out_of_range'] == 1
        reading = Reading.objects.get()
        assert reading.hors_plage is True
        # La donnée d'origine est conservée.
        assert reading.valeur == 150

    def test_preprocess_unknown_sensor(self, api_client, admin_user):
        api_client.force_authenticate(admin_user)
        r = api_client.post('/api/readings/preprocess/', {'sensor': 'NOPE'}, format='json')
        assert r.status_code == 404


# ── UC-12 : permissions par rôle ──────────────────────────────────────────────

@pytest.mark.django_db
class TestPermissions:
    def test_20_admin_full_access(self, api_client, admin_user, machine):
        api_client.force_authenticate(admin_user)
        payload = {**SENSOR_PAYLOAD, 'machine': machine.id}
        assert api_client.post('/api/equipements/capteurs/', payload).status_code == 201

    def test_20_technicien_can_update_not_create(self, api_client, tech_user, machine, sensor):
        api_client.force_authenticate(tech_user)
        assert api_client.get('/api/equipements/capteurs/').status_code == 200
        assert api_client.patch(
            f'/api/equipements/capteurs/{sensor.id}/', {'nom': 'MAJ tech'}
        ).status_code == 200
        payload = {**SENSOR_PAYLOAD, 'machine': machine.id}
        assert api_client.post('/api/equipements/capteurs/', payload).status_code == 403
        assert api_client.delete(f'/api/equipements/capteurs/{sensor.id}/').status_code == 403

    def test_20_operateur_read_only_sensors(self, api_client, op_user, machine):
        api_client.force_authenticate(op_user)
        assert api_client.get('/api/equipements/capteurs/').status_code == 200
        payload = {**SENSOR_PAYLOAD, 'machine': machine.id}
        assert api_client.post('/api/equipements/capteurs/', payload).status_code == 403

    def test_20_technicien_can_ingest_readings(self, api_client, tech_user, sensor):
        api_client.force_authenticate(tech_user)
        r = api_client.post('/api/readings/', {
            'sensor': 'TEMP-001', 'value': 50, 'timestamp': '2026-10-03T10:30:00Z',
        }, format='json')
        assert r.status_code == 201

    def test_20_operateur_cannot_ingest(self, api_client, op_user, sensor):
        api_client.force_authenticate(op_user)
        r = api_client.post('/api/readings/', {
            'sensor': 'TEMP-001', 'value': 50, 'timestamp': '2026-10-03T10:30:00Z',
        }, format='json')
        assert r.status_code == 403

    def test_20_operateur_cannot_import(self, api_client, op_user, sensor):
        api_client.force_authenticate(op_user)
        f = make_readings_csv([
            {'sensor_id': 'TEMP-001', 'timestamp': '2026-10-03T10:00:00Z', 'value': '1'},
        ])
        r = api_client.post('/api/equipements/readings/import_csv/', {'file': f}, format='multipart')
        assert r.status_code == 403

    def test_20_unauthenticated_forbidden(self, api_client, sensor):
        assert api_client.get('/api/equipements/capteurs/').status_code == 401
        assert api_client.get('/api/readings/').status_code == 401


# ── Lecture des mesures ───────────────────────────────────────────────────────

@pytest.mark.django_db
class TestReadingList:
    def test_list_readings_filter_by_sensor(self, api_client, admin_user, sensor):
        Reading.objects.create(
            sensor=sensor, valeur=42,
            timestamp=datetime(2026, 10, 3, 10, 0, tzinfo=dt_timezone.utc),
        )
        api_client.force_authenticate(admin_user)
        r = api_client.get(f'/api/equipements/readings/?sensor={sensor.id}')
        assert r.status_code == 200
        assert r.data['count'] == 1
