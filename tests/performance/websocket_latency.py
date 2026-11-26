"""Measure reading-ingest to WebSocket delivery latency against a live test API."""
import argparse
from datetime import datetime, timezone
import json
import math
import os
import statistics
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import websocket


def request_json(url, *, method='GET', payload=None, token=None):
    body = None if payload is None else json.dumps(payload).encode('utf-8')
    headers = {'Content-Type': 'application/json'}
    if token:
        headers['Authorization'] = f'Bearer {token}'
    req = Request(url, data=body, headers=headers, method=method)
    with urlopen(req, timeout=10) as response:
        data = response.read()
        return response.status, json.loads(data) if data else None


def percentile(values, percent):
    ordered = sorted(values)
    return ordered[max(0, math.ceil(percent / 100 * len(ordered)) - 1)]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--api', default=os.getenv('PERF_API_URL', 'http://127.0.0.1:8000'))
    parser.add_argument('--ws', default=os.getenv('PERF_WS_URL', 'ws://127.0.0.1:8000'))
    parser.add_argument('--iterations', type=int, default=30)
    parser.add_argument('--sensor-id', type=int, default=None)
    args = parser.parse_args()
    email, password = os.getenv('LOCUST_EMAIL'), os.getenv('LOCUST_PASSWORD')
    if not email or not password:
        raise SystemExit('Définir LOCUST_EMAIL et LOCUST_PASSWORD pour le compte ADMIN de recette.')
    if args.iterations < 1 or args.iterations > 1000:
        raise SystemExit('--iterations doit être compris entre 1 et 1000.')

    api = args.api.rstrip('/')
    _, login = request_json(f'{api}/api/auth/login/', method='POST', payload={'email': email, 'password': password})
    token = login['access']
    sensor_id = args.sensor_id
    if sensor_id is None:
        _, page = request_json(f'{api}/api/equipements/capteurs/?search=PERF-SENSOR-&page_size=200', token=token)
        results = page.get('results', []) if isinstance(page, dict) else page
        if not results:
            raise SystemExit('Aucun capteur PERF trouvé. Exécuter d’abord seed_load_data.py sur la base dédiée.')
        sensor_id = results[0]['id']

    ws_url = f"{args.ws.rstrip('/')}/ws/readings/{sensor_id}/?token={token}"
    samples_ms = []
    failures = []
    for index in range(args.iterations):
        ws = websocket.create_connection(ws_url, timeout=5, origin=args.api.rstrip('/'))
        started = time.perf_counter()
        try:
            status, _ = request_json(
                f'{api}/api/equipements/readings/',
                method='POST', token=token,
                payload={'sensor': sensor_id, 'value': 20 + (index % 50), 'timestamp': datetime.now(timezone.utc).isoformat()},
            )
            if status != 201:
                failures.append(f'itération {index + 1}: POST HTTP {status}')
                continue
            payload = json.loads(ws.recv())
            if payload.get('sensor') != sensor_id:
                failures.append(f'itération {index + 1}: capteur reçu inattendu')
                continue
            samples_ms.append((time.perf_counter() - started) * 1000)
        except (HTTPError, URLError, TimeoutError, websocket.WebSocketException, ValueError) as exc:
            failures.append(f'itération {index + 1}: {type(exc).__name__}: {exc}')
        finally:
            ws.close()

    print(json.dumps({
        'sensor_id': sensor_id,
        'requested_iterations': args.iterations,
        'successful_samples': len(samples_ms),
        'failures': failures,
        'latency_ms': ({
            'min': round(min(samples_ms), 2),
            'median': round(statistics.median(samples_ms), 2),
            'p95': round(percentile(samples_ms, 95), 2),
            'max': round(max(samples_ms), 2),
        } if samples_ms else None),
        'criterion_ms': 2000,
    }, indent=2, ensure_ascii=False))
    if failures or not samples_ms:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
