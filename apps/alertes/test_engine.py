import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import Utilisateur
from apps.alertes.engine import evaluer_seuil
from apps.alertes.models import Alerte
from apps.equipements.models import Machine, Reading, Sensor


@pytest.mark.parametrize(
    ('value', 'expected_type', 'expected_threshold', 'expected_excess', 'expected_ratio'),
    [
        (5, Alerte.TypeAlerte.SEUIL_MIN, 10.0, 5.0, 6.25),
        (10, None, None, None, None),
        (90, None, None, None, None),
        (100, Alerte.TypeAlerte.SEUIL_MAX, 90.0, 10.0, 12.5),
    ],
)
def test_legacy_complete_threshold_detection_is_unchanged(
    value, expected_type, expected_threshold, expected_excess, expected_ratio,
):
    """Capteurs existants avec min/max : mêmes comparaisons strictes et ratio de plage."""
    result = evaluer_seuil(value, seuil_min=10, seuil_max=90)

    if expected_type is None:
        assert result is None
        return

    assert result == {
        'type_alerte': expected_type,
        'seuil': expected_threshold,
        'depassement': expected_excess,
        'ratio_plage_pct': expected_ratio,
    }


@pytest.mark.parametrize(
    ('value', 'minimum', 'maximum', 'expected_type'),
    [
        (5, 10, None, Alerte.TypeAlerte.SEUIL_MIN),
        (11, 10, None, None),
        (11, None, 10, Alerte.TypeAlerte.SEUIL_MAX),
        (9, None, 10, None),
        (9, None, None, None),
    ],
)
def test_partial_threshold_detection_and_ratio(value, minimum, maximum, expected_type):
    result = evaluer_seuil(value, seuil_min=minimum, seuil_max=maximum)
    if expected_type is None:
        assert result is None
    else:
        assert result['type_alerte'] == expected_type
        assert result['ratio_plage_pct'] == 0.0


@pytest.mark.django_db
def test_reading_api_creates_then_resolves_max_only_alert_with_open_ended_message():
    machine = Machine.objects.create(nom='Pompe seuil partiel', identifiant_interne='P-ALERT-PARTIAL')
    sensor = Sensor.objects.create(
        identifiant='TEMP-MAX-ONLY', nom='Température max seule', type_capteur='TEMPERATURE',
        machine=machine, unite='°C', frequence_mesure=60, seuil_min=None, seuil_max=10,
    )
    admin = Utilisateur.objects.create_user(
        email='partial-threshold-admin@test.local', password='pass', role='ADMIN', nom='Admin', prenom='Test',
    )
    client = APIClient()
    client.force_authenticate(admin)
    base = timezone.now()

    outside = client.post('/api/readings/', {
        'sensor': sensor.identifiant, 'value': 11, 'timestamp': base.isoformat(),
    }, format='json')
    assert outside.status_code == 201, outside.data
    alert = Alerte.objects.get(capteur=sensor)
    assert alert.type_alerte == Alerte.TypeAlerte.SEUIL_MAX
    assert alert.statut == Alerte.Statut.ACTIVE

    normal = client.post('/api/readings/', {
        'sensor': sensor.identifiant, 'value': 10, 'timestamp': (base + timezone.timedelta(seconds=1)).isoformat(),
    }, format='json')
    assert normal.status_code == 201, normal.data
    alert.refresh_from_db()
    assert alert.statut == Alerte.Statut.RESOLVED
    assert '−∞ – 10.0 °C' in alert.message_resolution

    min_only = Sensor.objects.create(
        identifiant='TEMP-MIN-ONLY', nom='Température min seule', type_capteur='TEMPERATURE',
        machine=machine, unite='°C', frequence_mesure=60, seuil_min=10, seuil_max=None,
    )
    client.post('/api/readings/', {
        'sensor': min_only.identifiant, 'value': 9,
        'timestamp': (base + timezone.timedelta(seconds=2)).isoformat(),
    }, format='json')
    min_alert = Alerte.objects.get(capteur=min_only)
    client.post('/api/readings/', {
        'sensor': min_only.identifiant, 'value': 10,
        'timestamp': (base + timezone.timedelta(seconds=3)).isoformat(),
    }, format='json')
    min_alert.refresh_from_db()
    assert min_alert.statut == Alerte.Statut.RESOLVED
    assert '10.0 – +∞ °C' in min_alert.message_resolution
