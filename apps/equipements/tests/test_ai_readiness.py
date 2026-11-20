import io

import pytest
from django.core.exceptions import ValidationError
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import override_settings
from rest_framework.test import APIClient

from apps.accounts.models import Utilisateur
from apps.equipements.models import Machine, Reading, Sensor, Usine, Zone, LigneProduction, UserScope
from apps.equipements.sensors_io import import_sensors_from_csv


@pytest.fixture
def readiness_setup(db):
    factory = Usine.objects.create(nom='Usine readiness')
    zone = Zone.objects.create(nom='Zone readiness', usine=factory)
    line = LigneProduction.objects.create(nom='Ligne readiness', zone=zone)
    machine = Machine.objects.create(nom='Pompe readiness', identifiant_interne='P-READY', ligne_production=line)
    sensor = Sensor.objects.create(
        identifiant='TEMP-READY', nom='Température readiness', type_capteur='TEMPERATURE',
        machine=machine, unite='°C', frequence_mesure=60, seuil_min=None, seuil_max=100,
        sensor_role='temperature', nominal_min=10, nominal_max=90, is_ai_eligible=True,
    )
    return machine, sensor


@pytest.mark.django_db
def test_sensor_metadata_validation_and_partial_thresholds(readiness_setup):
    machine, _ = readiness_setup
    valid = Sensor(identifiant='VIB-OK', nom='Vibration', type_capteur='VIBRATION', machine=machine,
                   unite='mm/s', frequence_mesure=60, seuil_min=0, seuil_max=None,
                   sensor_role='vibration', nominal_min=1, nominal_max=8, is_ai_eligible=True)
    valid.full_clean()
    invalid = Sensor(identifiant='TEMP-BAD', nom='Température', type_capteur='TEMPERATURE', machine=machine,
                     unite='bar', frequence_mesure=60, sensor_role='temperature')
    with pytest.raises(ValidationError, match='incompatible'):
        invalid.full_clean()


@pytest.mark.django_db
def test_ai_eligible_requires_role_and_nominal_range(readiness_setup):
    machine, _ = readiness_setup
    sensor = Sensor(identifiant='OTHER-AI', nom='Autre', type_capteur='TEMPERATURE', machine=machine,
                    unite='unité historique', frequence_mesure=30, is_ai_eligible=True)
    with pytest.raises(ValidationError) as error:
        sensor.full_clean()
    assert 'is_ai_eligible' in error.value.message_dict


@pytest.mark.django_db
def test_sensor_serializer_supports_unit_and_sampling_period_aliases(readiness_setup):
    machine, _ = readiness_setup
    admin = Utilisateur.objects.create_user(email='alias-admin@test.local', password='pass', role='ADMIN', nom='A', prenom='A')
    client = APIClient()
    client.force_authenticate(admin)
    response = client.post('/api/equipements/capteurs/', {
        'identifiant': 'ALIAS-API', 'nom': 'Alias', 'type_capteur': 'TEMPERATURE',
        'machine': machine.pk, 'unit': '°C', 'sampling_period_seconds': 15,
        'sensor_role': 'temperature', 'nominal_min': 10, 'nominal_max': 40,
        'seuil_min': None, 'seuil_max': 50,
    }, format='json')
    assert response.status_code == 201, response.data
    assert response.data['unit'] == response.data['unite'] == '°C'
    assert response.data['sampling_period_seconds'] == response.data['frequence_mesure'] == 15


@pytest.mark.django_db(transaction=True)
def test_migration_supplies_safe_defaults_for_existing_sensors():
    executor = MigrationExecutor(connection)
    latest = executor.loader.graph.leaf_nodes()
    old_target = ('equipements', '0009_work_orders_and_recurring_maintenance')
    new_target = ('equipements', '0010_sensor_ai_metadata')
    executor.migrate([old_target])
    old_apps = executor.loader.project_state([old_target]).apps
    OldMachine = old_apps.get_model('equipements', 'Machine')
    OldSensor = old_apps.get_model('equipements', 'Sensor')
    machine = OldMachine.objects.create(nom='Machine avant migration', identifiant_interne='MIGRATION-01')
    sensor = OldSensor.objects.create(
        identifiant='SENSOR-MIGRATION-01', nom='Capteur historique', type_capteur='TEMPERATURE',
        machine=machine, unite='ancienne-unité', frequence_mesure=60, seuil_min=0, seuil_max=100,
    )
    sensor_id = sensor.pk
    try:
        executor = MigrationExecutor(connection)
        executor.migrate([new_target])
        new_apps = executor.loader.project_state([new_target]).apps
        migrated = new_apps.get_model('equipements', 'Sensor').objects.get(pk=sensor_id)
        assert migrated.sensor_role == 'other'
        assert migrated.nominal_min is None and migrated.nominal_max is None
        assert migrated.criticality == 'low'
        assert migrated.is_ai_eligible is False
        assert migrated.unite == 'ancienne-unité'
    finally:
        MigrationExecutor(connection).migrate(latest)


@pytest.mark.django_db
def test_legacy_sensor_csv_without_ai_columns_is_accepted(readiness_setup):
    _, _ = readiness_setup
    csv_file = io.BytesIO(
        b'sensor_id,name,machine_identifiant,type,unit,frequency_seconds,threshold_min,threshold_max\n'
        b'LEGACY-CSV,Ancien capteur,P-READY,TEMPERATURE,unit-old,60,,,\n'
    )
    csv_file.name = 'legacy.csv'
    report = import_sensors_from_csv(csv_file)
    assert report['imported'] == 1
    sensor = Sensor.objects.get(identifiant='LEGACY-CSV')
    assert sensor.sensor_role == 'other'
    assert sensor.is_ai_eligible is False
    assert sensor.seuil_min is sensor.seuil_max is None


@pytest.mark.django_db
def test_sensor_csv_accepts_optional_ai_metadata(readiness_setup):
    _, _ = readiness_setup
    csv_file = io.BytesIO(
        ('sensor_id,name,machine_identifiant,type,unit,frequency_seconds,threshold_min,threshold_max,sensor_role,nominal_min,nominal_max,criticality,is_ai_eligible\n'
         'NEW-CSV,Température,P-READY,TEMPERATURE,°C,60,0,100,temperature,10,90,high,true\n').encode('utf-8')
    )
    csv_file.name = 'new.csv'
    report = import_sensors_from_csv(csv_file)
    assert report['imported'] == 1
    sensor = Sensor.objects.get(identifiant='NEW-CSV')
    assert sensor.is_ai_eligible and sensor.nominal_min == 10


@pytest.mark.django_db
@override_settings(AI_READINESS_MIN_HISTORY_DAYS=0, AI_READINESS_MIN_VALID_MEASURES=2, AI_READINESS_MAX_MISSING_RATE=50)
def test_readiness_returns_criteria_metrics_and_scopes(readiness_setup):
    machine, sensor = readiness_setup
    from django.utils import timezone
    now = timezone.now()
    Reading.objects.create(sensor=sensor, valeur=20, timestamp=now)
    Reading.objects.create(sensor=sensor, valeur=21, timestamp=now + timezone.timedelta(minutes=2))
    admin = Utilisateur.objects.create_user(email='ready-admin@test.local', password='pass', role='ADMIN', nom='A', prenom='A')
    operator = Utilisateur.objects.create_user(email='ready-op@test.local', password='pass', role='OPERATEUR', nom='O', prenom='O')
    client = APIClient()
    client.force_authenticate(admin)
    response = client.get('/api/ai/readiness/')
    assert response.status_code == 200
    assert response.data['criteria'] == {
        'min_history_days': 0, 'min_valid_measures': 2, 'max_missing_rate_percent': 50,
    }
    assert response.data['machines'][0]['machine_id'] == machine.pk
    assert response.data['machines'][0]['valid_measure_count'] == 2
    assert response.data['machines'][0]['missing_rate_percent'] == 33.3333
    client.force_authenticate(operator)
    assert client.get('/api/ai/readiness/').status_code == 403


@pytest.mark.django_db
def test_readiness_null_period_reports_unknown(readiness_setup):
    machine, sensor = readiness_setup
    sensor.frequence_mesure = None
    sensor.save()
    admin = Utilisateur.objects.create_user(email='ready-admin2@test.local', password='pass', role='ADMIN', nom='A', prenom='A')
    client = APIClient()
    client.force_authenticate(admin)
    result = client.get('/api/ai/readiness/').data['machines'][0]
    assert result['missing_rate_percent'] is None
    assert 'période d’échantillonnage inconnue' in result['blocking_reasons']


@pytest.mark.django_db
def test_technician_readiness_is_limited_to_user_scope(readiness_setup):
    machine, _ = readiness_setup
    outside = Machine.objects.create(nom='Pompe hors périmètre', identifiant_interne='P-OUTSIDE', ligne_production=machine.ligne_production)
    admin = Utilisateur.objects.create_user(email='ready-admin3@test.local', password='pass', role='ADMIN', nom='A', prenom='A')
    tech = Utilisateur.objects.create_user(email='ready-tech@test.local', password='pass', role='TECHNICIEN', nom='T', prenom='T')
    UserScope.objects.create(utilisateur=tech, machine=machine)
    client = APIClient()
    client.force_authenticate(admin)
    all_machines = client.get('/api/ai/readiness/').data['machines']
    assert {item['machine_id'] for item in all_machines} == {machine.pk, outside.pk}
    client.force_authenticate(tech)
    scoped = client.get('/api/ai/readiness/')
    assert scoped.status_code == 200
    assert [item['machine_id'] for item in scoped.data['machines']] == [machine.pk]
