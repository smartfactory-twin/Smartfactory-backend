"""Reproducible API and dashboard workload for a dedicated test deployment.

Run with 20 users for two minutes after seed_load_data.py creates 50 machines
and 500 sensors. The dashboard transaction follows DashboardPage's current
read requests; it is an API composition timing, not browser paint timing.
"""
from datetime import datetime, timedelta, timezone
import os
import time

from locust import HttpUser, between, task


class SmartFactoryApiUser(HttpUser):
    wait_time = between(0.5, 1.5)

    def on_start(self):
        email = os.getenv('LOCUST_EMAIL')
        password = os.getenv('LOCUST_PASSWORD')
        if not email or not password:
            raise RuntimeError('Définir LOCUST_EMAIL et LOCUST_PASSWORD pour le test de charge.')

        response = self.client.post(
            '/api/auth/login/',
            json={'email': email, 'password': password},
            name='POST /api/auth/login/',
        )
        if response.status_code != 200:
            raise RuntimeError(f'Connexion Locust refusée ({response.status_code}).')
        token = response.json().get('access')
        if not token:
            raise RuntimeError('La réponse de connexion ne contient pas le JWT access.')
        self.client.headers.update({'Authorization': f'Bearer {token}'})

    @task(5)
    def list_machines(self):
        self.client.get('/api/equipements/machines/', name='GET machines')

    @task(4)
    def list_sensors(self):
        self.client.get('/api/equipements/capteurs/', name='GET capteurs')

    @task(3)
    def list_alerts(self):
        self.client.get('/api/alertes/', name='GET alertes')

    @task(2)
    def my_profile(self):
        self.client.get('/api/auth/me/', name='GET profil')

    @task(2)
    def dashboard_api_composition(self):
        """Time the aggregate API requests used by the ADMIN dashboard."""
        started = time.perf_counter()
        total_bytes = 0
        failures = []

        def get(path, *, name, params=None):
            nonlocal total_bytes
            response = self.client.get(path, params=params, name=name)
            total_bytes += len(response.content)
            if response.status_code >= 400:
                failures.append(f'{name}: HTTP {response.status_code}')
            return response

        plants_response = get('/api/equipements/usines/', name='Dashboard component: usines')
        get('/api/auth/users/list/', name='Dashboard component: users', params={'actif': 'true'})
        today = datetime.now(timezone.utc).date()
        start = datetime.combine(today - timedelta(days=6), datetime.min.time(), tzinfo=timezone.utc)
        end = datetime.combine(today + timedelta(days=1), datetime.min.time(), tzinfo=timezone.utc) - timedelta(milliseconds=1)
        get('/api/alertes/tableau-de-bord/', name='Dashboard component: alert summary', params={
            'date_declenchement__gte': start.isoformat(),
            'date_declenchement__lte': end.isoformat(),
        })
        get('/api/equipements/machines/statistiques/', name='Dashboard component: machine status counts')
        get('/api/alertes/', name='Dashboard component: latest alerts', params={
            'statut': 'ACTIVE', 'ordering': '-date_declenchement', 'page_size': 5,
        })

        try:
            payload = plants_response.json()
            plants = payload.get('results', payload) if isinstance(payload, dict) else payload
            for plant in plants if isinstance(plants, list) else []:
                get(
                    f"/api/equipements/usines/{plant['id']}/hierarchie/",
                    name='Dashboard component: plant hierarchy',
                )
        except (ValueError, KeyError, TypeError):
            failures.append('usines: réponse JSON invalide')

        elapsed_ms = (time.perf_counter() - started) * 1000
        self.environment.events.request.fire(
            request_type='COMPOSITE',
            name='Dashboard composition (API, hors rendu navigateur)',
            response_time=elapsed_ms,
            response_length=total_bytes,
            response=None,
            context={},
            exception=RuntimeError('; '.join(failures)) if failures else None,
        )
