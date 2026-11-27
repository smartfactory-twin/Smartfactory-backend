from datetime import timedelta

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import Utilisateur
from apps.alertes.models import Alerte, Notification
from apps.equipements.models import LigneProduction, Machine, Sensor, Usine, UserScope, Zone


@pytest.mark.django_db
def test_existing_alert_and_notification_routes_keep_scope_and_response_shape():
    usine = Usine.objects.create(nom='Usine route test')
    zone = Zone.objects.create(nom='Zone route test', usine=usine)
    ligne = LigneProduction.objects.create(nom='Ligne route test', zone=zone)
    visible_machine = Machine.objects.create(
        nom='Pompe visible', identifiant_interne='POMPE-VISIBLE', ligne_production=ligne,
    )
    hidden_machine = Machine.objects.create(
        nom='Pompe cachée', identifiant_interne='POMPE-CACHEE', ligne_production=ligne,
    )
    visible_sensor = Sensor.objects.create(
        identifiant='TEMP-VISIBLE', nom='Température visible', type_capteur='TEMPERATURE',
        machine=visible_machine, unite='°C', frequence_mesure=60, seuil_min=0, seuil_max=80,
    )
    hidden_sensor = Sensor.objects.create(
        identifiant='TEMP-CACHE', nom='Température cachée', type_capteur='TEMPERATURE',
        machine=hidden_machine, unite='°C', frequence_mesure=60, seuil_min=0, seuil_max=80,
    )
    operator = Utilisateur.objects.create_user(
        email='route-operator@test.local', password='Test@123456',
        role='OPERATEUR', nom='Route', prenom='Test',
    )
    UserScope.objects.create(utilisateur=operator, machine=visible_machine)
    now = timezone.now()
    visible_alert = Alerte.objects.create(
        machine=visible_machine, capteur=visible_sensor, valeur=90, seuil=80,
        unite='°C', message='Dépassement', derniere_occurrence=now,
        date_declenchement=now,
    )
    Alerte.objects.create(
        machine=hidden_machine, capteur=hidden_sensor, valeur=90, seuil=80,
        unite='°C', message='Hors périmètre', derniere_occurrence=now,
        date_declenchement=now,
    )
    Notification.objects.create(
        utilisateur=operator, alerte=visible_alert,
        titre='Alerte visible', message='Dépassement',
    )

    client = APIClient()
    client.force_authenticate(operator)

    alerts = client.get('/api/alertes/')
    assert alerts.status_code == 200
    assert alerts.data['count'] == 1
    assert {'count', 'next', 'previous', 'results'} <= set(alerts.data)
    assert alerts.data['results'][0]['machine'] == visible_machine.id
    assert {'niveau_label', 'statut_label', 'machine_nom', 'capteur_nom', 'message'} <= set(alerts.data['results'][0])

    detail = client.get(f'/api/alertes/{visible_alert.id}/')
    assert detail.status_code == 200
    assert detail.data['lecture'] is None
    assert client.get(f"/api/alertes/{visible_alert.id + 999}/").status_code == 404

    alert_counter = client.get('/api/alertes/compteur/')
    assert alert_counter.status_code == 200
    assert set(alert_counter.data) == {'actives', 'critiques'}
    assert alert_counter.data['actives'] == 1

    notifications = client.get('/api/notifications/')
    assert notifications.status_code == 200
    assert {'count', 'next', 'previous', 'results'} <= set(notifications.data)
    assert notifications.data['results'][0]['alerte'] == visible_alert.id
    assert client.get('/api/notifications/compteur/').data == {'non_lues': 1}


@pytest.mark.django_db
def test_alert_aggregation_route_is_additive_and_rejects_unbounded_period():
    client = APIClient()
    response = client.get('/api/alertes/aggregation/par-machine/')
    assert response.status_code == 401

    admin = Utilisateur.objects.create_user(
        email='route-admin@test.local', password='Test@123456',
        role='ADMIN', nom='Route', prenom='Admin',
    )
    client.force_authenticate(admin)
    now = timezone.now()
    response = client.get('/api/alertes/aggregation/par-machine/', {
        'date_debut': (now - timedelta(days=367)).isoformat(),
        'date_fin': now.isoformat(),
    })
    assert response.status_code == 400


@pytest.mark.django_db
def test_dashboard_alert_stats_return_scoped_counts_and_daily_series():
    usine = Usine.objects.create(nom='Usine dashboard')
    zone = Zone.objects.create(nom='Zone dashboard', usine=usine)
    ligne = LigneProduction.objects.create(nom='Ligne dashboard', zone=zone)
    machine = Machine.objects.create(
        nom='Machine dashboard', identifiant_interne='MCH-DASHBOARD', ligne_production=ligne,
    )
    hidden_machine = Machine.objects.create(nom='Machine hors scope', identifiant_interne='MCH-DASHBOARD-HIDDEN')
    sensor = Sensor.objects.create(
        identifiant='TEMP-DASHBOARD', nom='Température', type_capteur='TEMPERATURE',
        machine=machine, unite='°C', frequence_mesure=60, seuil_min=0, seuil_max=80,
    )
    hidden_sensor = Sensor.objects.create(
        identifiant='TEMP-DASHBOARD-HIDDEN', nom='Température cachée', type_capteur='TEMPERATURE',
        machine=hidden_machine, unite='°C', frequence_mesure=60, seuil_min=0, seuil_max=80,
    )
    operator = Utilisateur.objects.create_user(
        email='dashboard-operator@test.local', password='Test@123456',
        role='OPERATEUR', nom='Dashboard', prenom='Test',
    )
    UserScope.objects.create(utilisateur=operator, machine=machine)
    now = timezone.now()
    Alerte.objects.create(
        machine=machine, capteur=sensor, valeur=90, seuil=80, niveau=Alerte.Niveau.CRITIQUE,
        statut=Alerte.Statut.ACTIVE, unite='°C', message='Visible',
        derniere_occurrence=now, date_declenchement=now,
    )
    Alerte.objects.create(
        machine=hidden_machine, capteur=hidden_sensor, valeur=90, seuil=80,
        statut=Alerte.Statut.ACTIVE, unite='°C', message='Cachée',
        derniere_occurrence=now, date_declenchement=now,
    )

    client = APIClient()
    client.force_authenticate(operator)
    params = {
        'date_declenchement__gte': (now - timedelta(days=1)).isoformat(),
        'date_declenchement__lte': (now + timedelta(days=1)).isoformat(),
    }
    response = client.get('/api/alertes/tableau-de-bord/', params)
    assert response.status_code == 200
    assert response.data['actives'] == 1
    assert response.data['machines_en_alerte'] == 1
    assert response.data['critiques'] == 1
    assert response.data['par_niveau'] == {Alerte.Niveau.CRITIQUE: 1}
    assert response.data['par_jour'] == [{'date': timezone.localdate().isoformat(), 'total': 1}]

    invalid = client.get('/api/alertes/tableau-de-bord/', {
        'date_declenchement__gte': 'not-a-date',
        'date_declenchement__lte': 'also-not-a-date',
    })
    assert invalid.status_code == 400
