import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.equipements.ai_prediction_views import _score
from apps.accounts.models import Utilisateur
from apps.equipements.models import Machine, Reading, Sensor
from apps.equipements.readings_io import (
    apply_preprocessing, import_readings_from_json, interpolate_sensor_readings,
)
from apps.equipements.reporting_views import _machine_health


@pytest.fixture
def threshold_sensor(db):
    machine = Machine.objects.create(nom='Machine seuil nullable', identifiant_interne='NULL-THRESHOLD-01')
    return Sensor.objects.create(
        identifiant='SENSOR-NULL-THRESHOLD', nom='Capteur max seul', type_capteur='TEMPERATURE',
        machine=machine, unite='°C', frequence_mesure=30, seuil_min=None, seuil_max=10,
    )


@pytest.mark.django_db
def test_preprocessing_and_json_ingestion_ignore_missing_minimum(threshold_sensor):
    sensor = threshold_sensor
    reading = Reading.objects.create(sensor=sensor, valeur=11, timestamp=timezone.now())
    apply_preprocessing(reading)
    assert reading.hors_plage is True
    assert reading.est_valide is False

    report = import_readings_from_json([{
        'sensor_id': sensor.identifiant, 'value': 12,
        'timestamp': (timezone.now() + timezone.timedelta(seconds=1)).isoformat(),
    }])
    assert report['imported'] == 1
    assert report['out_of_range'] == 1
    imported = Reading.objects.get(sensor=sensor, valeur=12)
    assert imported.hors_plage is True

    sensor.seuil_max = None
    sensor.save()
    unbounded = Reading.objects.create(
        sensor=sensor, valeur=999, timestamp=timezone.now() + timezone.timedelta(seconds=2),
    )
    apply_preprocessing(unbounded)
    assert unbounded.hors_plage is False


@pytest.mark.django_db
def test_interpolation_ignores_missing_minimum(threshold_sensor):
    sensor = threshold_sensor
    start = timezone.now()
    Reading.objects.create(sensor=sensor, valeur=11, timestamp=start)
    Reading.objects.create(sensor=sensor, valeur=13, timestamp=start + timezone.timedelta(seconds=60))

    assert interpolate_sensor_readings(sensor) == 1
    middle = Reading.objects.get(sensor=sensor, timestamp=start + timezone.timedelta(seconds=30))
    assert middle.valeur == 12
    assert middle.hors_plage is True


@pytest.mark.django_db
@pytest.mark.parametrize('minimum, maximum', [(None, 10), (0, None), (None, None)])
def test_statistical_ai_score_accepts_partial_or_absent_thresholds(threshold_sensor, minimum, maximum):
    sensor = threshold_sensor
    sensor.seuil_min = minimum
    sensor.seuil_max = maximum
    assert _score(sensor, 100, [10, 10, 10]) == 1.0


@pytest.mark.django_db
def test_anomaly_and_what_if_endpoints_handle_incomplete_thresholds(threshold_sensor):
    sensor = threshold_sensor
    now = timezone.now()
    for offset, value in enumerate((8, 9, 9.5)):
        Reading.objects.create(sensor=sensor, valeur=value, timestamp=now + timezone.timedelta(seconds=offset))
    admin = Utilisateur.objects.create_user(
        email='threshold-ml-admin@test.local', password='pass', role='ADMIN', nom='Admin', prenom='IA',
    )
    client = APIClient()
    client.force_authenticate(admin)

    anomaly = client.get(f'/api/ai-predictions/anomalies/?machine_id={sensor.machine_id}')
    assert anomaly.status_code == 200
    what_if = client.post('/api/ai-predictions/what-if/', {
        'sensor_id': sensor.pk, 'variation_percent': 10,
    }, format='json')
    assert what_if.status_code == 200
    assert isinstance(what_if.data['score_after'], float)


@pytest.mark.django_db
def test_machine_health_report_accepts_partial_thresholds(threshold_sensor):
    sensor = threshold_sensor
    now = timezone.now()
    Reading.objects.create(sensor=sensor, valeur=8, timestamp=now)
    Reading.objects.create(sensor=sensor, valeur=12, timestamp=now + timezone.timedelta(seconds=1))

    report = _machine_health(sensor.machine, now - timezone.timedelta(days=1))

    assert report['nombre_mesures'] == 2
    assert report['sante'] == 50
    assert report['capteurs'][0]['seuil_max'] == 10


@pytest.mark.django_db
def test_machine_health_is_unknown_when_no_thresholds_are_configured(threshold_sensor):
    sensor = threshold_sensor
    sensor.seuil_max = None
    sensor.save()
    Reading.objects.create(sensor=sensor, valeur=8, timestamp=timezone.now())

    report = _machine_health(sensor.machine, timezone.now() - timezone.timedelta(days=1))

    assert report['nombre_mesures'] == 1
    assert report['sante'] is None
