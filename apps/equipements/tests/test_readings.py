"""
UC-13 — Tests for readings API endpoints
Run with: pytest apps/equipements/tests/test_readings.py -v
"""
import pytest
from django.urls import reverse
from django.utils import timezone
from datetime import timedelta
from rest_framework.test import APIClient
from apps.accounts.models import User
from apps.equipements.models import Machine, Capteur, Reading


@pytest.fixture
def admin_user(db):
    return User.objects.create_user(
        email="admin@test.com", password="Test@1234", role="ADMIN"
    )


@pytest.fixture
def client_auth(admin_user):
    client = APIClient()
    res = client.post("/api/v1/auth/login/", {"email": "admin@test.com", "password": "Test@1234"})
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {res.data['access']}")
    return client


@pytest.fixture
def machine(db, admin_user):
    return Machine.objects.create(
        nom="Compresseur A1", id_interne="M01",
        zone="A", statut="actif", createur=admin_user
    )


@pytest.fixture
def capteur(db, machine):
    return Capteur.objects.create(
        machine=machine, nom="Température", unite="°C",
        type_capteur="temp", seuil_min=30, seuil_max=90,
    )


@pytest.fixture
def readings(db, capteur):
    now = timezone.now()
    readings = []
    for i in range(10):
        readings.append(Reading(
            capteur=capteur,
            valeur=65.0 + i,
            timestamp=now - timedelta(hours=10 - i),
        ))
    Reading.objects.bulk_create(readings)
    return readings


class TestReadingsListView:
    def test_requires_auth(self, client, machine):
        url = f"/api/v1/equipements/machines/{machine.pk}/readings/"
        res = client.get(url)
        assert res.status_code == 401

    def test_returns_series_dict(self, client_auth, machine, capteur, readings):
        url = f"/api/v1/equipements/machines/{machine.pk}/readings/?range=24h"
        res = client_auth.get(url)
        assert res.status_code == 200
        assert "results" in res.data
        assert str(capteur.pk) in res.data["results"]

    def test_points_format(self, client_auth, machine, capteur, readings):
        url = f"/api/v1/equipements/machines/{machine.pk}/readings/?range=24h"
        res = client_auth.get(url)
        pts = res.data["results"][str(capteur.pk)]
        assert len(pts) > 0
        assert len(pts[0]) == 2        # [timestamp_ms, value]
        assert isinstance(pts[0][0], int)   # timestamp is int
        assert isinstance(pts[0][1], float) # value is float

    def test_range_filter_1h(self, client_auth, machine, capteur, readings):
        url = f"/api/v1/equipements/machines/{machine.pk}/readings/?range=1h"
        res = client_auth.get(url)
        pts = res.data["results"].get(str(capteur.pk), [])
        # Only readings within last 1 hour
        assert len(pts) <= 2

    def test_404_unknown_machine(self, client_auth):
        res = client_auth.get("/api/v1/equipements/machines/99999/readings/?range=24h")
        assert res.status_code == 404

    def test_sensor_filter(self, client_auth, machine, capteur, readings):
        url = f"/api/v1/equipements/machines/{machine.pk}/readings/?range=24h&sensor={capteur.pk}"
        res = client_auth.get(url)
        assert str(capteur.pk) in res.data["results"]


class TestReadingCreateView:
    def test_create_reading(self, client_auth, capteur):
        res = client_auth.post("/api/v1/equipements/readings/", {
            "capteur": capteur.pk,
            "valeur": 72.5,
        })
        assert res.status_code == 201
        assert res.data["valeur"] == 72.5

    def test_missing_fields(self, client_auth):
        res = client_auth.post("/api/v1/equipements/readings/", {"capteur": 1})
        assert res.status_code == 400

    def test_out_of_range_value(self, client_auth, capteur):
        # seuil_max=90, so 90*2=180 → 200 should be rejected
        res = client_auth.post("/api/v1/equipements/readings/", {
            "capteur": capteur.pk,
            "valeur": 200,
        })
        assert res.status_code == 400

    def test_requires_auth(self, client, capteur):
        res = client.post("/api/v1/equipements/readings/", {
            "capteur": capteur.pk, "valeur": 72.5,
        })
        assert res.status_code == 401


class TestReadingsExportCSV:
    def test_returns_csv(self, client_auth, machine, capteur, readings):
        url = f"/api/v1/equipements/machines/{machine.pk}/readings/export/?range=24h"
        res = client_auth.get(url)
        assert res.status_code == 200
        assert "text/csv" in res["Content-Type"]
        content = res.content.decode("utf-8")
        assert "timestamp_utc" in content
        assert "Température" in content
