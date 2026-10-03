"""Tests Module 3 — UC-08 : import CSV de création de capteurs.

Vérifie que l'import de capteurs crée bien des ``Sensor`` (et jamais des
mesures), que les machines ne sont jamais créées automatiquement, et que
l'import des mesures IoT (UC-09) reste intact.
"""
import csv
import io

import pytest
from rest_framework.test import APIClient

from apps.accounts.models import Utilisateur
from apps.equipements.models import (
    Usine, Zone, LigneProduction, Machine, Sensor,
)

IMPORT_URL = '/api/equipements/capteurs/import_csv/'
PREVIEW_URL = '/api/equipements/capteurs/preview_csv/'

SENSOR_HEADERS = [
    'sensor_id', 'name', 'machine_identifiant', 'type', 'unit',
    'frequency_seconds', 'threshold_min', 'threshold_max', 'active', 'description',
]


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def admin_user(db):
    return Utilisateur.objects.create_user(
        email='m3-import-admin@smartfactory.com', password='Admin@123!',
        role='ADMIN', nom='Admin', prenom='Import',
    )


@pytest.fixture
def tech_user(db):
    return Utilisateur.objects.create_user(
        email='m3-import-tech@smartfactory.com', password='Tech@123!',
        role='TECHNICIEN', nom='Tech', prenom='Import',
    )


@pytest.fixture
def op_user(db):
    return Utilisateur.objects.create_user(
        email='m3-import-op@smartfactory.com', password='Op@123!',
        role='OPERATEUR', nom='Op', prenom='Import',
    )


@pytest.fixture
def machines(db):
    usine = Usine.objects.create(nom='Usine Import')
    zone = Zone.objects.create(nom='Zone Import', usine=usine)
    ligne = LigneProduction.objects.create(nom='Ligne Import', zone=zone)
    m1 = Machine.objects.create(
        nom='Tour CNC 101', identifiant_interne='CNC-101',
        statut='NORMAL', ligne_production=ligne,
    )
    m2 = Machine.objects.create(
        nom='Tour CNC 102', identifiant_interne='CNC-102',
        statut='NORMAL', ligne_production=ligne,
    )
    return m1, m2


def make_sensors_csv(rows, fieldnames=None):
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=fieldnames or SENSOR_HEADERS)
    writer.writeheader()
    for row in rows:
        writer.writerow(row)
    output.seek(0)
    file_bytes = io.BytesIO(output.read().encode('utf-8'))
    file_bytes.name = 'capteurs_test.csv'
    return file_bytes


def row(sensor_id, machine_identifiant, name=None, type_='TEMPERATURE',
        unit='°C', frequency='60', tmin='10', tmax='90', active='true',
        description=''):
    return {
        'sensor_id': sensor_id,
        'name': name if name is not None else f'Capteur {sensor_id}',
        'machine_identifiant': machine_identifiant,
        'type': type_,
        'unit': unit,
        'frequency_seconds': frequency,
        'threshold_min': tmin,
        'threshold_max': tmax,
        'active': active,
        'description': description,
    }


# ── Création de capteurs ──────────────────────────────────────────────────────

@pytest.mark.django_db
class TestSensorImport:
    def test_01_import_creates_sensors_and_associates_machine(
        self, api_client, admin_user, machines
    ):
        api_client.force_authenticate(admin_user)
        f = make_sensors_csv([
            row('TEMP-CNC-101', 'CNC-101'),
            row('VIB-CNC-101', 'CNC-101', type_='VIBRATION', unit='mm/s'),
            row('TEMP-CNC-102', 'CNC-102'),
        ])
        r = api_client.post(IMPORT_URL, {'file': f}, format='multipart')

        assert r.status_code == 200
        assert r.data['imported'] == 3
        assert r.data['rejected'] == 0
        assert r.data['duplicates'] == 0
        assert Sensor.objects.count() == 3

        s = Sensor.objects.get(identifiant='TEMP-CNC-101')
        assert s.machine.identifiant_interne == 'CNC-101'
        assert s.type_capteur == 'TEMPERATURE'
        assert s.unite == '°C'
        assert s.frequence_mesure == 60
        assert s.seuil_min == 10
        assert s.seuil_max == 90
        assert s.actif is True

    def test_02_import_ten_sensors(self, api_client, admin_user, machines):
        api_client.force_authenticate(admin_user)
        rows = [
            row(f'TEMP-CNC-{i:03d}', 'CNC-101' if i % 2 else 'CNC-102')
            for i in range(1, 11)
        ]
        r = api_client.post(IMPORT_URL, {'file': make_sensors_csv(rows)},
                            format='multipart')
        assert r.status_code == 200
        assert r.data['imported'] == 10
        assert Sensor.objects.count() == 10

    def test_03_frequency_seconds_not_converted(self, api_client, admin_user, machines):
        api_client.force_authenticate(admin_user)
        f = make_sensors_csv([row('TEMP-CNC-101', 'CNC-101', frequency='300')])
        api_client.post(IMPORT_URL, {'file': f}, format='multipart')
        assert Sensor.objects.get(identifiant='TEMP-CNC-101').frequence_mesure == 300

    def test_04_active_false_and_alias_statut(self, api_client, admin_user, machines):
        api_client.force_authenticate(admin_user)
        f = make_sensors_csv([
            row('TEMP-CNC-101', 'CNC-101', active='false'),
        ])
        api_client.post(IMPORT_URL, {'file': f}, format='multipart')
        assert Sensor.objects.get(identifiant='TEMP-CNC-101').actif is False

        # Ancien en-tête « statut » avec valeur INACTIF.
        legacy_headers = [
            'sensor_id', 'nom', 'machine_identifiant', 'type_capteur', 'unite',
            'frequence_mesure', 'seuil_min', 'seuil_max', 'statut',
        ]
        f2 = make_sensors_csv([{
            'sensor_id': 'VIB-CNC-101', 'nom': 'Vibration', 'machine_identifiant': 'CNC-101',
            'type_capteur': 'VIBRATION', 'unite': 'mm/s', 'frequence_mesure': '5',
            'seuil_min': '0', 'seuil_max': '50', 'statut': 'INACTIF',
        }], fieldnames=legacy_headers)
        api_client.post(IMPORT_URL, {'file': f2}, format='multipart')
        assert Sensor.objects.get(identifiant='VIB-CNC-101').actif is False

    def test_05_name_defaults_to_sensor_id(self, api_client, admin_user, machines):
        api_client.force_authenticate(admin_user)
        f = make_sensors_csv([{**row('TEMP-CNC-101', 'CNC-101'), 'name': ''}])
        api_client.post(IMPORT_URL, {'file': f}, format='multipart')
        assert Sensor.objects.get(identifiant='TEMP-CNC-101').nom == 'TEMP-CNC-101'

    def test_06_semicolon_delimiter(self, api_client, admin_user, machines):
        api_client.force_authenticate(admin_user)
        content = (
            'sensor_id;name;machine_identifiant;type;unit;'
            'frequency_seconds;threshold_min;threshold_max;active;description\n'
            'TEMP-CNC-101;Temp;CNC-101;TEMPERATURE;°C;60;10;90;true;\n'
        )
        f = io.BytesIO(content.encode('utf-8'))
        f.name = 'capteurs_pointvirgule.csv'
        r = api_client.post(IMPORT_URL, {'file': f}, format='multipart')
        assert r.status_code == 200
        assert r.data['imported'] == 1

    def test_06b_frequence_minutes_converted_to_seconds(
        self, api_client, admin_user, machines
    ):
        """L'ancien en-tête frequence_minutes est accepté et converti (× 60)."""
        api_client.force_authenticate(admin_user)
        headers = [
            'sensor_id', 'name', 'machine_identifiant', 'type', 'unit',
            'frequence_minutes', 'seuil_min', 'seuil_max', 'active',
        ]
        f = make_sensors_csv([{
            'sensor_id': 'TEMP-CNC-101', 'name': 'Temp', 'machine_identifiant': 'CNC-101',
            'type': 'TEMPERATURE', 'unit': '°C', 'frequence_minutes': '1',
            'seuil_min': '10', 'seuil_max': '90', 'active': 'true',
        }], fieldnames=headers)
        r = api_client.post(IMPORT_URL, {'file': f}, format='multipart')
        assert r.status_code == 200
        assert r.data['imported'] == 1
        assert Sensor.objects.get(identifiant='TEMP-CNC-101').frequence_mesure == 60

    def test_06b2_legacy_header_with_machine_nom_unite_seuils_statut(
        self, api_client, admin_user, machines
    ):
        """En-tête historique complet : unite/seuil_*/statut/frequence_minutes."""
        api_client.force_authenticate(admin_user)
        headers = [
            'sensor_id', 'type', 'machine_identifiant', 'machine_nom', 'unite',
            'frequence_minutes', 'seuil_min', 'seuil_max', 'statut',
        ]
        rows = [
            {
                'sensor_id': f'TEMP-CNC-10{i}', 'type': 'TEMPERATURE',
                'machine_identifiant': 'CNC-101', 'machine_nom': 'Tour CNC 101',
                'unite': '°C', 'frequence_minutes': '1', 'seuil_min': '10',
                'seuil_max': '90', 'statut': 'ACTIF',
            }
            for i in range(1, 6)
        ]
        r = api_client.post(IMPORT_URL, {'file': make_sensors_csv(rows, fieldnames=headers)},
                            format='multipart')
        assert r.status_code == 200
        assert r.data['imported'] == 5
        assert r.data['rejected'] == 0
        s = Sensor.objects.get(identifiant='TEMP-CNC-101')
        assert s.unite == '°C'
        assert s.frequence_mesure == 60  # 1 minute → 60 secondes
        assert s.seuil_min == 10
        assert s.seuil_max == 90
        assert s.actif is True
        assert s.nom == 'TEMP-CNC-101'  # pas de colonne name → sensor_id

    def test_06c_frequency_seconds_takes_precedence_over_minutes(
        self, api_client, admin_user, machines
    ):
        api_client.force_authenticate(admin_user)
        headers = [
            'sensor_id', 'name', 'machine_identifiant', 'type', 'unit',
            'frequency_seconds', 'frequence_minutes', 'seuil_min', 'seuil_max', 'active',
        ]
        f = make_sensors_csv([{
            'sensor_id': 'TEMP-CNC-101', 'name': 'Temp', 'machine_identifiant': 'CNC-101',
            'type': 'TEMPERATURE', 'unit': '°C', 'frequency_seconds': '90',
            'frequence_minutes': '1', 'seuil_min': '10', 'seuil_max': '90', 'active': 'true',
        }], fieldnames=headers)
        api_client.post(IMPORT_URL, {'file': f}, format='multipart')
        assert Sensor.objects.get(identifiant='TEMP-CNC-101').frequence_mesure == 90


# ── Rejets / doublons ─────────────────────────────────────────────────────────

@pytest.mark.django_db
class TestSensorImportRejections:
    def test_07_machine_not_found(self, api_client, admin_user, machines):
        api_client.force_authenticate(admin_user)
        f = make_sensors_csv([row('TEMP-CNC-999', 'CNC-999')])
        r = api_client.post(IMPORT_URL, {'file': f}, format='multipart')
        assert r.status_code == 200
        assert r.data['imported'] == 0
        assert r.data['rejected'] == 1
        assert Sensor.objects.count() == 0
        assert 'Machine introuvable : CNC-999' in r.data['errors'][0]['message']

    def test_08_never_creates_machine(self, api_client, admin_user, machines):
        api_client.force_authenticate(admin_user)
        before = Machine.objects.count()
        f = make_sensors_csv([row('TEMP-CNC-999', 'CNC-999')])
        api_client.post(IMPORT_URL, {'file': f}, format='multipart')
        assert Machine.objects.count() == before

    def test_09_missing_sensor_id(self, api_client, admin_user, machines):
        api_client.force_authenticate(admin_user)
        f = make_sensors_csv([{**row('', 'CNC-101'), 'sensor_id': ''}])
        r = api_client.post(IMPORT_URL, {'file': f}, format='multipart')
        assert r.data['rejected'] == 1
        assert r.data['errors'][0]['message'] == 'sensor_id requis'

    def test_10_invalid_type(self, api_client, admin_user, machines):
        api_client.force_authenticate(admin_user)
        f = make_sensors_csv([row('TEMP-CNC-101', 'CNC-101', type_='INCONNU')])
        r = api_client.post(IMPORT_URL, {'file': f}, format='multipart')
        assert r.data['rejected'] == 1
        assert 'Type de capteur invalide' in r.data['errors'][0]['message']
        assert Sensor.objects.count() == 0

    def test_11_missing_machine_identifiant(self, api_client, admin_user, machines):
        api_client.force_authenticate(admin_user)
        f = make_sensors_csv([{**row('TEMP-CNC-101', 'CNC-101'), 'machine_identifiant': ''}])
        r = api_client.post(IMPORT_URL, {'file': f}, format='multipart')
        assert r.data['rejected'] == 1
        assert 'machine_identifiant requis' in r.data['errors'][0]['message']

    def test_12_invalid_thresholds(self, api_client, admin_user, machines):
        api_client.force_authenticate(admin_user)
        f = make_sensors_csv([row('TEMP-CNC-101', 'CNC-101', tmin='90', tmax='10')])
        r = api_client.post(IMPORT_URL, {'file': f}, format='multipart')
        assert r.data['rejected'] == 1
        assert 'seuil minimum' in r.data['errors'][0]['message']

    def test_13_existing_sensor_is_duplicate(self, api_client, admin_user, machines):
        m1, _ = machines
        Sensor.objects.create(
            identifiant='TEMP-CNC-101', nom='Existant', type_capteur='TEMPERATURE',
            machine=m1, unite='°C', frequence_mesure=60, seuil_min=0, seuil_max=100,
        )
        api_client.force_authenticate(admin_user)
        f = make_sensors_csv([row('TEMP-CNC-101', 'CNC-101')])
        r = api_client.post(IMPORT_URL, {'file': f}, format='multipart')
        assert r.data['imported'] == 0
        assert r.data['duplicates'] == 1
        assert 'Capteur déjà existant : TEMP-CNC-101' in r.data['errors'][0]['message']
        assert Sensor.objects.filter(identifiant='TEMP-CNC-101').count() == 1

    def test_14_duplicate_within_file(self, api_client, admin_user, machines):
        api_client.force_authenticate(admin_user)
        f = make_sensors_csv([
            row('TEMP-CNC-101', 'CNC-101'),
            row('TEMP-CNC-101', 'CNC-102'),
        ])
        r = api_client.post(IMPORT_URL, {'file': f}, format='multipart')
        assert r.data['imported'] == 1
        assert r.data['duplicates'] == 1
        assert Sensor.objects.count() == 1


# ── Prévisualisation ──────────────────────────────────────────────────────────

@pytest.mark.django_db
class TestSensorImportPreview:
    def test_15_preview_does_not_insert(self, api_client, admin_user, machines):
        api_client.force_authenticate(admin_user)
        f = make_sensors_csv([
            row('TEMP-CNC-101', 'CNC-101'),
            row('TEMP-CNC-999', 'CNC-999'),
        ])
        r = api_client.post(PREVIEW_URL, {'file': f}, format='multipart')
        assert r.status_code == 200
        assert r.data['imported'] == 1
        assert r.data['rejected'] == 1
        assert Sensor.objects.count() == 0

    def test_16_preview_items_shape(self, api_client, admin_user, machines):
        api_client.force_authenticate(admin_user)
        f = make_sensors_csv([row('TEMP-CNC-101', 'CNC-101')])
        r = api_client.post(PREVIEW_URL, {'file': f}, format='multipart')
        assert r.status_code == 200
        item = r.data['preview_items'][0]
        assert item['sensor_id'] == 'TEMP-CNC-101'
        assert item['machine_identifiant'] == 'CNC-101'
        assert item['type'] == 'TEMPERATURE'
        assert item['unit'] == '°C'
        assert item['frequency_seconds'] == 60
        assert item['threshold_min'] == 10
        assert item['threshold_max'] == 90
        assert item['active'] is True

    def test_17_preview_reports_detected_columns(self, api_client, admin_user, machines):
        api_client.force_authenticate(admin_user)
        f = make_sensors_csv([row('TEMP-CNC-101', 'CNC-101')])
        r = api_client.post(PREVIEW_URL, {'file': f}, format='multipart')
        assert r.status_code == 200
        assert 'frequency_seconds' in r.data['columns']
        assert 'machine_identifiant' in r.data['columns']


# ── Permissions / alias / non-régression ──────────────────────────────────────

@pytest.mark.django_db
class TestSensorImportPermissions:
    def test_17_technicien_forbidden(self, api_client, tech_user, machines):
        api_client.force_authenticate(tech_user)
        f = make_sensors_csv([row('TEMP-CNC-101', 'CNC-101')])
        r = api_client.post(IMPORT_URL, {'file': f}, format='multipart')
        assert r.status_code == 403
        assert Sensor.objects.count() == 0

    def test_18_operateur_forbidden(self, api_client, op_user, machines):
        api_client.force_authenticate(op_user)
        f = make_sensors_csv([row('TEMP-CNC-101', 'CNC-101')])
        assert api_client.post(IMPORT_URL, {'file': f}, format='multipart').status_code == 403
        assert api_client.post(PREVIEW_URL, {'file': f}, format='multipart').status_code == 403

    def test_19_unauthenticated_forbidden(self, api_client, machines):
        f = make_sensors_csv([row('TEMP-CNC-101', 'CNC-101')])
        assert api_client.post(IMPORT_URL, {'file': f}, format='multipart').status_code == 401

    def test_20_alias_route(self, api_client, admin_user, machines):
        api_client.force_authenticate(admin_user)
        f = make_sensors_csv([row('TEMP-CNC-101', 'CNC-101')])
        r = api_client.post('/api/capteurs/import_csv/', {'file': f}, format='multipart')
        assert r.status_code == 200
        assert r.data['imported'] == 1

    def test_21_no_file_provided(self, api_client, admin_user):
        api_client.force_authenticate(admin_user)
        r = api_client.post(IMPORT_URL, {}, format='multipart')
        assert r.status_code == 400

    def test_22_readings_import_still_works(self, api_client, admin_user, machines):
        """Non-régression : l'import de mesures IoT reste séparé et fonctionnel."""
        m1, _ = machines
        Sensor.objects.create(
            identifiant='TEMP-CNC-101', nom='Temp', type_capteur='TEMPERATURE',
            machine=m1, unite='°C', frequence_mesure=60, seuil_min=0, seuil_max=100,
        )
        api_client.force_authenticate(admin_user)
        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=['sensor_id', 'timestamp', 'value'])
        writer.writeheader()
        writer.writerow({
            'sensor_id': 'TEMP-CNC-101',
            'timestamp': '2026-10-03T10:00:00Z',
            'value': '65.2',
        })
        f = io.BytesIO(output.getvalue().encode('utf-8'))
        f.name = 'mesures.csv'
        r = api_client.post('/api/equipements/readings/import_csv/',
                            {'file': f}, format='multipart')
        assert r.status_code == 200
        assert r.data['imported'] == 1
        assert 'Capteurs importés' not in r.data
