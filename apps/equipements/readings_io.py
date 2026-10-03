"""Module 3 — UC-09 / UC-10 : Ingestion et prétraitement des mesures de capteurs.

Ce module est distinct de `csv_hierarchy.py` (Module 2).
- Module 2 : CSV → Usine / Zone / Ligne / Machine / Composant
- Module 3 : CSV / JSON → Lectures de capteurs (Sensor readings)

Règles de prétraitement (UC-10) :
- RULE 1 : valeurs hors plage (seuil_min / seuil_max) → marquées `hors_plage`,
  la donnée d'origine n'est jamais supprimée silencieusement.
- RULE 2 : données manquantes. Les trous < 5 minutes sont interpolés,
  les trous >= 5 minutes ne sont pas inventés.
- RULE 3 : tous les timestamps sont normalisés et stockés en UTC.
"""
from __future__ import annotations

import csv
import io
from datetime import datetime, timedelta, timezone as dt_timezone

from django.utils.dateparse import parse_datetime

from .models import Sensor, Reading

# Seuil de trou au-delà duquel on n'interpole pas (UC-10, RULE 2).
INTERPOLATION_GAP = timedelta(minutes=5)


# ── Utilitaires ───────────────────────────────────────────────────────────────

def normalize_timestamp(value):
    """Convertit une valeur quelconque en datetime *aware* UTC.

    Lève ``ValueError`` si la valeur est invalide.
    """
    if value is None:
        raise ValueError('Timestamp manquant.')

    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, (int, float)) and not isinstance(value, bool):
        dt = datetime.fromtimestamp(float(value), tz=dt_timezone.utc)
    else:
        raw = str(value).strip()
        if not raw:
            raise ValueError('Timestamp vide.')
        # Remplacement du suffixe « Z » par un offset explicite.
        if raw.endswith('Z'):
            raw = raw[:-1] + '+00:00'
        dt = parse_datetime(raw)
        if dt is None:
            try:
                dt = datetime.fromisoformat(raw)
            except ValueError as exc:
                raise ValueError(f'Timestamp invalide : {value}') from exc

    # Normalisation UTC : un timestamp naïf est considéré comme UTC.
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=dt_timezone.utc)
    return dt.astimezone(dt_timezone.utc)


def _parse_value(raw):
    if raw is None:
        raise ValueError('Valeur manquante.')
    if isinstance(raw, bool):
        raise ValueError(f'Valeur non numérique : {raw}')
    try:
        return float(str(raw).strip())
    except (TypeError, ValueError) as exc:
        raise ValueError(f'Valeur non numérique : {raw}') from exc


def _extract_keys(item):
    """Récupère sensor/value/timestamp en tolérant plusieurs alias de colonnes."""
    sensor_id = (
        item.get('sensor_id')
        or item.get('sensor')
        or item.get('sensor_identifiant')
        or item.get('identifiant_capteur')
        or item.get('capteur_id')
        or item.get('capteur')
    )
    value = item.get('value', item.get('valeur', item.get('mesure')))
    timestamp = item.get('timestamp', item.get('horodatage', item.get('date')))
    return sensor_id, value, timestamp


def apply_preprocessing(reading: Reading) -> Reading:
    """RULE 1 : marque une lecture hors plage sans la supprimer."""
    sensor = reading.sensor
    out_of_range = reading.valeur < sensor.seuil_min or reading.valeur > sensor.seuil_max
    reading.hors_plage = out_of_range
    reading.est_valide = not out_of_range
    reading.save(update_fields=['hors_plage', 'est_valide'])
    return reading


# ── Analyse / import ──────────────────────────────────────────────────────────

def _process_items(items, dry_run=False):
    """Analyse puis (optionnellement) insère une liste de mesures.

    Retourne un rapport d'import stable pour l'API :
    imported, rejected, duplicates, out_of_range, interpolated, errors, total_rows.
    """
    imported = 0
    rejected = 0
    duplicates = 0
    out_of_range = 0
    errors = []
    already_seen = set()

    for index, item in enumerate(items, start=1):
        if not isinstance(item, dict):
            errors.append({'row': index, 'message': 'Ligne invalide (objet attendu).'})
            rejected += 1
            continue

        sensor_id, raw_value, raw_timestamp = _extract_keys(item)

        if not sensor_id:
            errors.append({'row': index, 'message': 'Le champ sensor_id est requis.'})
            rejected += 1
            continue

        try:
            sensor = Sensor.objects.get(identifiant=str(sensor_id).strip())
        except Sensor.DoesNotExist:
            errors.append({'row': index, 'message': f'Capteur introuvable : {sensor_id}'})
            rejected += 1
            continue

        try:
            value = _parse_value(raw_value)
        except ValueError as exc:
            errors.append({'row': index, 'message': str(exc)})
            rejected += 1
            continue

        try:
            timestamp = normalize_timestamp(raw_timestamp)
        except ValueError as exc:
            errors.append({'row': index, 'message': str(exc)})
            rejected += 1
            continue

        dedup_key = (sensor.id, timestamp, value)
        if dedup_key in already_seen:
            duplicates += 1
            continue
        already_seen.add(dedup_key)

        is_out_of_range = value < sensor.seuil_min or value > sensor.seuil_max

        if dry_run:
            if Reading.objects.filter(sensor=sensor, timestamp=timestamp, valeur=value).exists():
                duplicates += 1
                continue
            imported += 1
            if is_out_of_range:
                out_of_range += 1
            continue

        reading, created = Reading.objects.get_or_create(
            sensor=sensor,
            timestamp=timestamp,
            valeur=value,
        )
        if not created:
            duplicates += 1
            continue

        apply_preprocessing(reading)
        if reading.hors_plage:
            out_of_range += 1
        imported += 1

    return {
        'imported': imported,
        'rejected': rejected,
        'duplicates': duplicates,
        'out_of_range': out_of_range,
        # L'interpolation (UC-10, RULE 2) est déclenchée explicitement via
        # l'action `preprocess`, jamais silencieusement pendant l'ingestion.
        'interpolated': 0,
        'errors': errors,
        'total_rows': imported + rejected + duplicates,
    }


def import_readings_from_csv(file_obj, dry_run=False):
    """Importe des mesures depuis un fichier CSV (colonnes sensor_id, timestamp, value)."""
    raw = file_obj.read()
    content = None
    for encoding in ('utf-8-sig', 'utf-8', 'latin1', 'cp1252'):
        try:
            content = raw.decode(encoding)
            break
        except (UnicodeDecodeError, LookupError):
            continue
    if content is None:
        content = raw.decode('utf-8', errors='replace')

    first_line = content.split('\n', 1)[0] if content else ''
    delimiter = ';' if ';' in first_line and ',' not in first_line else ','
    items = list(csv.DictReader(io.StringIO(content), delimiter=delimiter))
    return _process_items(items, dry_run=dry_run)


def import_readings_from_json(data, dry_run=False):
    """Importe des mesures depuis une liste JSON de dicts."""
    if not isinstance(data, list):
        raise ValueError('Un tableau JSON est requis.')
    return _process_items(data, dry_run=dry_run)


# ── UC-10, RULE 2 : interpolation des trous < 5 minutes ───────────────────────

def interpolate_sensor_readings(sensor: Sensor) -> int:
    """Interpole les mesures manquantes quand le trou est < 5 minutes.

    Un trou est considéré comme « manquant » uniquement s'il est plus grand
    que la fréquence de mesure configurée (sinon aucun échantillon n'est perdu).
    Les trous >= 5 minutes ne génèrent aucune valeur inventée.

    Retourne le nombre de valeurs interpolées créées.
    """
    readings = list(
        Reading.objects.filter(sensor=sensor, interpolation=False)
        .order_by('timestamp')
        .values_list('timestamp', 'valeur')
    )
    if len(readings) < 2:
        return 0

    expected = timedelta(seconds=max(sensor.frequence_mesure, 1))
    created = 0

    for (t1, v1), (t2, v2) in zip(readings, readings[1:]):
        gap = t2 - t1
        if gap <= expected or gap >= INTERPOLATION_GAP:
            # Pas de perte d'échantillon, ou trou trop grand : aucune invention.
            continue

        nb_intervals = int(gap / expected)
        if nb_intervals < 2:
            continue

        for step in range(1, nb_intervals):
            ts = t1 + expected * step
            if ts >= t2:
                break
            if Reading.objects.filter(sensor=sensor, timestamp=ts).exists():
                continue

            ratio = (ts - t1).total_seconds() / gap.total_seconds()
            interpolated_value = v1 + (v2 - v1) * ratio
            Reading.objects.create(
                sensor=sensor,
                timestamp=ts,
                valeur=interpolated_value,
                interpolation=True,
                est_valide=True,
                hors_plage=(
                    interpolated_value < sensor.seuil_min
                    or interpolated_value > sensor.seuil_max
                ),
            )
            created += 1
    return created


# ── UC-10 : pipeline de prétraitement ─────────────────────────────────────────

def preprocess_readings(sensor=None):
    """Applique le prétraitement UC-10 à un capteur (ou à tous).

    - RULE 1 : (re)marque les valeurs hors plage **sans les supprimer**.
    - RULE 2 : interpole les trous < 5 minutes (aucune invention au-delà).

    Retourne un rapport : ``{sensors_processed, out_of_range, interpolated}``.
    """
    sensors = [sensor] if sensor is not None else list(Sensor.objects.all())

    out_of_range = 0
    interpolated = 0
    for current in sensors:
        for reading in Reading.objects.filter(sensor=current, interpolation=False):
            previously_out = reading.hors_plage
            apply_preprocessing(reading)
            if reading.hors_plage and not previously_out:
                out_of_range += 1

        interpolated += interpolate_sensor_readings(current)

    return {
        'sensors_processed': len(sensors),
        'out_of_range': out_of_range,
        'interpolated': interpolated,
    }
