from django.conf import settings
from django.db.models import Count, Max, Min, Q
from rest_framework.permissions import BasePermission, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Machine, Reading, Sensor
from .permissions import scope_queryset_machine


class AiReadinessRolePermission(BasePermission):
    message = "Cette ressource est réservée aux rôles ADMIN et TECHNICIEN."

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.role in ('ADMIN', 'TECHNICIEN'))


class AiReadinessAPIView(APIView):
    permission_classes = [IsAuthenticated, AiReadinessRolePermission]

    def get(self, request):
        criteria = {
            'min_history_days': settings.AI_READINESS_MIN_HISTORY_DAYS,
            'min_valid_measures': settings.AI_READINESS_MIN_VALID_MEASURES,
            'max_missing_rate_percent': settings.AI_READINESS_MAX_MISSING_RATE,
        }
        machines = list(scope_queryset_machine(Machine.objects.all(), request.user).order_by('id'))
        machine_ids = [m.pk for m in machines]
        sensors = list(Sensor.objects.filter(machine_id__in=machine_ids, is_ai_eligible=True).values(
            'id', 'machine_id', 'frequence_mesure', 'nominal_min', 'nominal_max', 'sensor_role'
        ))
        sensor_ids = [s['id'] for s in sensors]
        stats = {
            row['sensor_id']: row
            for row in Reading.objects.filter(sensor_id__in=sensor_ids, est_valide=True, interpolation=False)
            .values('sensor_id').annotate(
                valid_count=Count('id'), first=Min('timestamp'), last=Max('timestamp'),
                observed_timestamps=Count('timestamp', distinct=True),
            )
        }
        sensors_by_machine = {pk: [] for pk in machine_ids}
        for sensor in sensors:
            sensors_by_machine[sensor['machine_id']].append(sensor)

        results = []
        for machine in machines:
            machine_sensors = sensors_by_machine[machine.pk]
            reasons = []
            measure_count = 0
            first = last = None
            expected_total = observed_total = 0
            unknown_period = False
            for sensor in machine_sensors:
                period = sensor['frequence_mesure']
                if not period or period <= 0:
                    unknown_period = True
                stat = stats.get(sensor['id'])
                if not stat:
                    continue
                measure_count += stat['valid_count']
                first = min(first, stat['first']) if first else stat['first']
                last = max(last, stat['last']) if last else stat['last']
                if not period or period <= 0:
                    continue
                duration_seconds = max((stat['last'] - stat['first']).total_seconds(), 0)
                expected_total += int(duration_seconds // period) + 1
                observed_total += stat['observed_timestamps']

            history_seconds = max((last - first).total_seconds(), 0) if first and last else 0
            history_days = history_seconds / 86400
            if not machine_sensors:
                reasons.append('aucun capteur éligible')
            if unknown_period:
                reasons.append('période d’échantillonnage inconnue')
            missing_rate = None
            if unknown_period:
                missing_rate = None
            elif expected_total:
                missing_rate = max(0.0, min(100.0, (expected_total - observed_total) * 100.0 / expected_total))
            else:
                missing_rate = 100.0
            if measure_count < criteria['min_valid_measures']:
                reasons.append(f"mesures valides insuffisantes ({measure_count} < {criteria['min_valid_measures']})")
            if history_days < criteria['min_history_days']:
                reasons.append(f"historique insuffisant ({history_days:.2f} < {criteria['min_history_days']} jours)")
            if missing_rate is not None and missing_rate > criteria['max_missing_rate_percent']:
                reasons.append(f"taux de valeurs manquantes trop élevé ({missing_rate:.2f} %)")
            results.append({
                'machine_id': machine.pk,
                'machine': machine.nom,
                'machine_identifiant': machine.identifiant_interne,
                'eligible_sensor_count': len(machine_sensors),
                'valid_measure_count': measure_count,
                'history_days': round(history_days, 4),
                'missing_rate_percent': round(missing_rate, 4) if missing_rate is not None else None,
                'status': 'ready' if not reasons else 'blocked',
                'ready_for_training': not reasons,
                'blocking_reasons': reasons,
            })
        return Response({'criteria': criteria, 'machines': results})
