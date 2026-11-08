"""
UC-13 — Readings API views with time-range filtering
UC-14 — Multi-sensor data for overlay charts
UC-15 — CSV export endpoint
"""
from django.utils import timezone
from django.http import HttpResponse
from django.db.models import Q
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import status
from datetime import timedelta
import csv
import io

from .models import Machine, Capteur, Reading
from .broadcast import broadcast_reading


RANGE_DELTA = {
    "1h":  timedelta(hours=1),
    "6h":  timedelta(hours=6),
    "24h": timedelta(hours=24),
    "7j":  timedelta(days=7),
    "30j": timedelta(days=30),
}


class ReadingsListView(APIView):
    """
    GET  /api/v1/equipements/machines/<id>/readings/
    Query params:
      range   = 1h | 6h | 24h | 7j | 30j
      from    = ISO datetime  (custom range)
      to      = ISO datetime  (custom range)
      sensor  = capteur id    (repeatable, filters sensors)
      n       = max points per sensor (default 300)

    Response:
      { "results": { "<sensor_id>": [[timestamp_ms, value], ...] } }
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, machine_id):
        # Check machine exists and user has access
        try:
            machine = Machine.objects.get(pk=machine_id)
        except Machine.DoesNotExist:
            return Response({"detail": "Machine introuvable."}, status=404)

        # Time range
        now = timezone.now()
        range_key = request.query_params.get("range", "24h")
        if range_key in RANGE_DELTA:
            date_from = now - RANGE_DELTA[range_key]
            date_to   = now
        else:
            # Custom range
            try:
                from dateutil.parser import parse
                date_from = parse(request.query_params.get("from", ""))
                date_to   = parse(request.query_params.get("to", ""))
            except Exception:
                return Response({"detail": "Plage de dates invalide."}, status=400)

        # Sensor filter
        sensor_ids = request.query_params.getlist("sensor")
        capteurs_qs = Capteur.objects.filter(machine=machine)
        if sensor_ids:
            capteurs_qs = capteurs_qs.filter(pk__in=sensor_ids)

        # Max points (downsampling)
        n = int(request.query_params.get("n", 300))

        results = {}
        for capteur in capteurs_qs:
            readings = (
                Reading.objects
                .filter(capteur=capteur, timestamp__gte=date_from, timestamp__lte=date_to)
                .order_by("timestamp")
                .values_list("timestamp", "valeur")
            )
            pts = [[int(ts.timestamp() * 1000), float(v)] for ts, v in readings]

            # Simple uniform downsampling if too many points
            if len(pts) > n:
                step = len(pts) / n
                pts  = [pts[int(i * step)] for i in range(n)]

            results[str(capteur.pk)] = pts

        return Response({"results": results})


class ReadingCreateView(APIView):
    """
    POST /api/v1/equipements/readings/
    Ingest a single reading from IoT gateway + broadcast via WebSocket.

    Body: { "capteur": <id>, "valeur": <float>, "timestamp": "<ISO>" (optional) }
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        capteur_id = request.data.get("capteur")
        valeur     = request.data.get("valeur")

        if capteur_id is None or valeur is None:
            return Response({"detail": "capteur et valeur sont requis."}, status=400)

        try:
            capteur = Capteur.objects.select_related("machine").get(pk=capteur_id)
        except Capteur.DoesNotExist:
            return Response({"detail": "Capteur introuvable."}, status=404)

        # Timestamp
        raw_ts = request.data.get("timestamp")
        if raw_ts:
            from dateutil.parser import parse
            ts = parse(raw_ts)
        else:
            ts = timezone.now()

        # Validate range (UC-10 — filtering out-of-range values)
        valeur = float(valeur)
        if capteur.seuil_min is not None and valeur < capteur.seuil_min * 0.5:
            return Response({"detail": f"Valeur {valeur} hors plage (trop basse)."}, status=400)
        if capteur.seuil_max is not None and valeur > capteur.seuil_max * 2:
            return Response({"detail": f"Valeur {valeur} hors plage (trop haute)."}, status=400)

        # Save
        reading = Reading.objects.create(
            capteur=capteur,
            valeur=valeur,
            timestamp=ts,
        )

        # Broadcast to WebSocket group
        ts_ms = int(ts.timestamp() * 1000)
        broadcast_reading(
            machine_id=str(capteur.machine.pk),
            sensor_id=str(capteur.pk),
            timestamp_ms=ts_ms,
            value=valeur,
        )

        return Response({
            "id":        reading.pk,
            "capteur":   capteur.pk,
            "valeur":    valeur,
            "timestamp": ts.isoformat(),
        }, status=201)


class ReadingsExportCSVView(APIView):
    """
    UC-15 — GET /api/v1/equipements/machines/<id>/readings/export/
    Returns a CSV file with all sensor data for the given range.
    Same query params as ReadingsListView.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, machine_id):
        try:
            machine = Machine.objects.get(pk=machine_id)
        except Machine.DoesNotExist:
            return Response({"detail": "Machine introuvable."}, status=404)

        now = timezone.now()
        range_key = request.query_params.get("range", "24h")
        date_from = now - RANGE_DELTA.get(range_key, timedelta(hours=24))

        capteurs = Capteur.objects.filter(machine=machine).order_by("pk")

        output = io.StringIO()
        writer = csv.writer(output, delimiter=";")

        # Header
        header = ["timestamp_utc"] + [f"{c.nom}_{c.unite}" for c in capteurs]
        writer.writerow(header)

        # Collect all timestamps
        all_readings = {}
        for capteur in capteurs:
            readings = Reading.objects.filter(
                capteur=capteur, timestamp__gte=date_from
            ).order_by("timestamp").values_list("timestamp", "valeur")
            all_readings[capteur.pk] = {ts: v for ts, v in readings}

        all_ts = sorted(set(ts for readings in all_readings.values() for ts in readings))

        for ts in all_ts:
            row = [ts.isoformat()]
            for capteur in capteurs:
                v = all_readings[capteur.pk].get(ts)
                row.append(f"{v:.4f}" if v is not None else "")
            writer.writerow(row)

        output.seek(0)
        filename = f"readings_{machine.id_interne or machine_id}_{range_key}.csv"
        response = HttpResponse(output.getvalue(), content_type="text/csv")
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        return response
