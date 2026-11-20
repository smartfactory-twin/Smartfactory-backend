"""Charge API SmartFactory Twin; comptes dédiés de test via variables d'env.

Exemple : locust -f tests/performance/locustfile.py --host http://127.0.0.1:8000 \
  --users 20 --spawn-rate 5 --run-time 2m --headless --csv reports/locust
"""
import os

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

    @task(3)
    def list_alerts(self):
        self.client.get('/api/alertes/', name='GET alertes')

    @task(2)
    def my_profile(self):
        self.client.get('/api/auth/me/', name='GET profil')
