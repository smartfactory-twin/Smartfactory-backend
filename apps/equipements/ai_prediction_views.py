from datetime import timedelta
from statistics import median, pstdev

from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.alertes.models import Alerte
from .cmapss_ml import artifact_status
from .models import Machine, Reading, Sensor
from .permissions import scope_queryset_machine, scope_queryset_sensor


def _score(sensor, value, values):
    span = max(float(sensor.seuil_max - sensor.seuil_min), 1e-9)
    outside = max(0.0, (value - sensor.seuil_max) / span, (sensor.seuil_min - value) / span)
    center = median(values) if values else (sensor.seuil_min + sensor.seuil_max) / 2
    spread = pstdev(values) if len(values) > 1 else span / 6
    statistical = max(0.0, abs(value - center) / max(spread, span / 100) - 2) / 6
    return min(1.0, max(outside, statistical))


class AnomalyAnalysisAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        machine_id = request.query_params.get('machine_id')
        machine = get_object_or_404(scope_queryset_machine(Machine.objects.all(), request.user), pk=machine_id)
        since = timezone.now() - timedelta(hours=24)
        sensors = scope_queryset_sensor(Sensor.objects.filter(machine=machine, actif=True), request.user)
        series = {}
        latest_contributors = []
        for sensor in sensors:
            all_values = list(Reading.objects.filter(sensor=sensor, est_valide=True, timestamp__gte=since).values_list('valeur', flat=True)[:500])
            readings = list(Reading.objects.filter(sensor=sensor, est_valide=True, timestamp__gte=since).order_by('-timestamp')[:60])
            values = [float(v) for v in all_values]
            for reading in reversed(readings):
                score = _score(sensor, float(reading.valeur), values)
                key = reading.timestamp.isoformat()
                point = series.setdefault(key, {'timestamp': key, 'score': 0.0, 'contributors': []})
                if score > point['score']:
                    point['score'] = round(score, 3)
                if score >= 0.2:
                    point['contributors'].append({'sensor': sensor.nom, 'score': round(score, 3), 'value': reading.valeur, 'unit': sensor.unite})
            if readings:
                newest = readings[0]
                score = _score(sensor, float(newest.valeur), values)
                if score >= 0.2:
                    latest_contributors.append({'sensor': sensor.nom, 'score': round(score, 3), 'value': newest.valeur, 'unit': sensor.unite})

        points = sorted(series.values(), key=lambda point: point['timestamp'])[-60:]
        latest_score = points[-1]['score'] if points else 0.0
        history = Alerte.objects.filter(machine=machine, date_declenchement__gte=since).select_related('capteur').order_by('-date_declenchement')[:30]
        return Response({
            'machine': {'id': machine.id, 'nom': machine.nom},
            'threshold': 0.65,
            'score': latest_score,
            'detected': latest_score >= 0.65,
            'contributors': sorted(latest_contributors, key=lambda item: item['score'], reverse=True)[:5],
            'history': points,
            'alerts': [{
                'id': alert.id, 'timestamp': alert.date_declenchement, 'machine': machine.nom,
                'sensor': alert.capteur.nom, 'sensor_id': alert.capteur_id,
                'value': alert.valeur, 'threshold_value': alert.seuil, 'unit': alert.unite,
                'alert_type': alert.get_type_alerte_display(), 'level': alert.get_niveau_display(),
                'score': alert.anomalie_ia_score, 'status': alert.get_statut_display(),
                'message': alert.message, 'source': 'Seuil capteur',
                'occurrences': alert.nb_occurrences,
            } for alert in history],
            'method': 'Score statistique calculé à partir des seuils et de la dispersion des mesures sur 24 h. Aucun LSTM n’est activé.',
        })


class WhatIfAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        sensor_id = request.data.get('sensor_id')
        try:
            variation = float(request.data.get('variation_percent', 0))
        except (TypeError, ValueError):
            return Response({'detail': 'variation_percent doit être numérique.'}, status=status.HTTP_400_BAD_REQUEST)
        if not -100 <= variation <= 300:
            return Response({'detail': 'La variation doit être comprise entre -100 % et 300 %.'}, status=status.HTTP_400_BAD_REQUEST)
        sensor = get_object_or_404(scope_queryset_sensor(Sensor.objects.select_related('machine'), request.user), pk=sensor_id)
        latest = Reading.objects.filter(sensor=sensor, est_valide=True).order_by('-timestamp').first()
        if not latest:
            return Response({'detail': 'Ce capteur ne possède aucune mesure valide.'}, status=status.HTTP_400_BAD_REQUEST)
        recent = list(Reading.objects.filter(sensor=sensor, est_valide=True).order_by('-timestamp').values_list('valeur', flat=True)[:500])
        before = float(latest.valeur)
        after = before * (1 + variation / 100)
        base_score = _score(sensor, before, recent)
        simulated_score = _score(sensor, after, recent)
        return Response({
            'machine': sensor.machine.nom, 'sensor': sensor.nom, 'unit': sensor.unite,
            'variation_percent': variation, 'value_before': before, 'value_after': round(after, 3),
            'score_before': round(base_score, 3), 'score_after': round(simulated_score, 3),
            'threshold': 0.65, 'anomaly_after': simulated_score >= 0.65,
            'method': 'Simulation statistique sur la dernière mesure et les seuils du capteur; ne prédit pas de RUL.',
        })


class AiModelsAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        rul = artifact_status()
        metadata = rul.get('metadata') or {}
        metrics = metadata.get('official_test') or {}
        return Response({
            'models': [
                {'id': 'sensor-statistics', 'name': 'Score statistique d’anomalie', 'state': 'ACTIF', 'dataset': 'Mesures réelles enregistrées dans SmartFactory', 'metrics': None},
                {'id': 'lstm-autoencoder', 'name': 'LSTM Autoencoder', 'state': 'NON_ENTRAINE', 'dataset': 'Aucune série temporelle industrielle annotée configurée', 'metrics': None},
                {'id': 'cmapss-rul', 'name': rul.get('model_name', 'HistGradientBoostingRegressor'), 'state': 'PRET' if rul.get('ready') else 'NON_ENTRAINE', 'dataset': 'NASA C-MAPSS (turbofan simulé)', 'metrics': metrics, 'details': {key: metadata.get(key) for key in ('training_engines', 'training_rows', 'feature_count', 'window_size', 'rul_cap_cycles', 'validation') if key in metadata}, 'detail': rul.get('detail')},
            ],
            'note': 'Les performances ne sont pas inventées. Le score d’anomalie est statistique; le modèle C-MAPSS reste distinct des machines industrielles.',
        })
