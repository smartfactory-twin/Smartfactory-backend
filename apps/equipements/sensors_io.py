"""Module 3 — UC-08 : Import CSV de création de capteurs.

Ce module est **distinct** de ``readings_io.py`` :
- ``sensors_io.py``  : CSV → création de ``Sensor`` (cet import) ;
- ``readings_io.py`` : CSV / JSON → création de ``Reading`` (mesures IoT).

Règles :
- ``sensor_id`` est obligatoire et unique (aucun doublon créé) ;
- chaque ligne doit référencer une **machine existante** via
  ``machine_identifiant`` ; aucune machine n'est créée automatiquement ;
- seuls les types de capteurs déjà définis dans le projet sont acceptés ;
- ``frequency_seconds`` est déjà exprimé en secondes : aucune conversion.
"""
from __future__ import annotations

import csv
import io

from django.db import transaction

from .models import Machine, Sensor

# Colonnes canoniques attendues dans le CSV de capteurs.
SENSOR_CSV_COLUMNS = [
    'sensor_id', 'name', 'machine_identifiant', 'type', 'unit',
    'frequency_seconds', 'threshold_min', 'threshold_max', 'active', 'description',
]

# Alias de colonnes tolérés (dont les noms de champs du modèle).
SENSOR_HEADER_ALIASES = {
    'sensor_id': 'sensor_id',
    'identifiant': 'sensor_id',
    'identifiant_capteur': 'sensor_id',
    'capteur': 'sensor_id',
    'capteur_id': 'sensor_id',
    'sensor': 'sensor_id',

    'name': 'name',
    'nom': 'name',
    'nom_capteur': 'name',

    'machine_identifiant': 'machine_identifiant',
    'identifiant_machine': 'machine_identifiant',
    'machine': 'machine_identifiant',
    'machine_id': 'machine_identifiant',

    'type': 'type',
    'type_capteur': 'type',

    'unit': 'unit',
    'unite': 'unit',

    'frequency_seconds': 'frequency_seconds',
    'frequence_seconds': 'frequency_seconds',
    'frequency_secondes': 'frequency_seconds',
    'frequence_secondes': 'frequency_seconds',
    'frequence_seconde': 'frequency_seconds',
    'frequence_mesure': 'frequency_seconds',
    'frequency': 'frequency_seconds',

    # Compatibilité : fréquence exprimée en minutes → convertie en secondes.
    'frequency_minutes': 'frequency_minutes',
    'frequence_minutes': 'frequency_minutes',
    'frequency_minute': 'frequency_minutes',
    'frequence_minute': 'frequency_minutes',

    'threshold_min': 'threshold_min',
    'seuil_min': 'threshold_min',

    'threshold_max': 'threshold_max',
    'seuil_max': 'threshold_max',

    'active': 'active',
    'actif': 'active',
    # Compatibilité avec l'ancien en-tête « statut » (actif/inactif).
    'statut': 'active',

    'description': 'description',
}

VALID_SENSOR_TYPES = [choice[0] for choice in Sensor.SensorType.choices]

TRUTHY = {'true', '1', 'oui', 'yes', 'actif', 'active', 'vrai'}
FALSY = {'false', '0', 'non', 'no', 'inactif', 'inactive', 'faux'}

# Nombre maximum d'éléments renvoyés dans l'aperçu.
PREVIEW_LIMIT = 50


# ── Utilitaires de lecture ────────────────────────────────────────────────────

def _decode(file_obj):
    """Décode un fichier CSV en testant plusieurs encodages courants."""
    raw = file_obj.read()
    for encoding in ('utf-8-sig', 'utf-8', 'latin1', 'cp1252'):
        try:
            return raw.decode(encoding)
        except (UnicodeDecodeError, LookupError):
            continue
    return raw.decode('utf-8', errors='replace')


def parse_sensor_csv(file_obj):
    """Lit un CSV de capteurs.

    Retourne ``(columns, rows)`` : la liste des en-têtes bruts et les lignes.
    """
    content = _decode(file_obj)
    first_line = content.split('\n', 1)[0] if content else ''
    delimiter = ';' if ';' in first_line and ',' not in first_line else ','
    reader = csv.DictReader(io.StringIO(content), delimiter=delimiter)
    rows = list(reader)
    return list(reader.fieldnames or []), rows


def _canonical_columns(columns):
    """Traduit les en-têtes bruts en noms de colonnes canoniques."""
    mapped = []
    for column in columns:
        if column is None:
            continue
        clean_key = column.strip().lower().replace(' ', '_').replace('-', '_')
        mapped.append(SENSOR_HEADER_ALIASES.get(clean_key, clean_key))
    return mapped


def normalize_sensor_row(raw_row):
    """Normalise les en-têtes et les valeurs d'une ligne CSV de capteurs."""
    normalized = {}
    for key, value in raw_row.items():
        if key is None:
            continue
        clean_key = key.strip().lower().replace(' ', '_').replace('-', '_')
        target_key = SENSOR_HEADER_ALIASES.get(clean_key, clean_key)
        if isinstance(value, str):
            value = value.strip()
        elif value is None:
            value = ''
        else:
            value = str(value).strip()
        normalized[target_key] = value
    return normalized


def _parse_int(raw, field, row_errors):
    if raw in (None, ''):
        row_errors.append(f'{field} requis')
        return None
    try:
        return int(float(str(raw).replace(',', '.')))
    except (TypeError, ValueError):
        row_errors.append(f'{field} invalide : {raw}')
        return None


def _parse_float(raw, field, row_errors):
    if raw in (None, ''):
        row_errors.append(f'{field} requis')
        return None
    try:
        return float(str(raw).replace(',', '.'))
    except (TypeError, ValueError):
        row_errors.append(f'{field} invalide : {raw}')
        return None


def _parse_bool(raw, row_errors):
    if raw in (None, ''):
        return True
    lowered = str(raw).strip().lower()
    if lowered in TRUTHY:
        return True
    if lowered in FALSY:
        return False
    row_errors.append(f'active invalide : {raw}')
    return None


def _resolve_frequency_seconds(normalized, row_errors):
    """Résout la fréquence en secondes.

    ``frequency_seconds`` est la colonne canonique (aucune conversion).
    Par compatibilité, ``frequence_minutes`` est acceptée et explicitement
    convertie en secondes (× 60), car l'en-tête indique des minutes.
    """
    raw_seconds = normalized.get('frequency_seconds', '')
    if raw_seconds not in (None, ''):
        value = _parse_int(raw_seconds, 'frequency_seconds', row_errors)
        if value is not None and value <= 0:
            row_errors.append('frequency_seconds doit être supérieur à 0')
        return value

    raw_minutes = normalized.get('frequency_minutes', '')
    if raw_minutes not in (None, ''):
        minutes = _parse_float(raw_minutes, 'frequence_minutes', row_errors)
        if minutes is None:
            return None
        if minutes <= 0:
            row_errors.append('frequence_minutes doit être supérieur à 0')
            return None
        return int(round(minutes * 60))

    row_errors.append('frequency_seconds requis')
    return None


# ── Analyse / import ──────────────────────────────────────────────────────────

def import_sensors_from_csv(file_obj, dry_run=False):
    """Analyse puis (optionnellement) crée des capteurs depuis un CSV.

    Retourne un rapport stable pour l'API :
    ``imported``, ``rejected``, ``duplicates``, ``errors``, ``total_rows``,
    ``preview_items``.
    """
    raw_columns, rows = parse_sensor_csv(file_obj)
    columns = _canonical_columns(raw_columns)

    imported = 0
    rejected = 0
    duplicates = 0
    errors = []
    preview_items = []
    valid_rows = []
    seen_ids = set()

    for index, raw_row in enumerate(rows, start=2):
        normalized = normalize_sensor_row(raw_row)
        # Ignore les lignes totalement vides.
        if not any(normalized.values()):
            continue

        sensor_id = normalized.get('sensor_id', '').strip()
        if not sensor_id:
            errors.append({'row': index, 'message': 'sensor_id requis'})
            rejected += 1
            continue

        # Doublon : déjà en base, ou déjà rencontré dans le fichier.
        already_exists = (
            sensor_id in seen_ids
            or Sensor.objects.filter(identifiant=sensor_id).exists()
        )
        if already_exists:
            errors.append({
                'row': index,
                'message': f'Capteur déjà existant : {sensor_id}',
            })
            duplicates += 1
            continue

        row_errors = []

        # ── Machine existante (jamais créée automatiquement) ──────────────
        machine_identifiant = normalized.get('machine_identifiant', '').strip()
        machine = None
        if not machine_identifiant:
            row_errors.append('machine_identifiant requis')
        else:
            machine = Machine.objects.filter(
                identifiant_interne=machine_identifiant
            ).first()
            if machine is None:
                row_errors.append(f'Machine introuvable : {machine_identifiant}')

        # ── Type de capteur ───────────────────────────────────────────────
        sensor_type = normalized.get('type', '').strip().upper()
        if not sensor_type or sensor_type not in VALID_SENSOR_TYPES:
            row_errors.append('Type de capteur invalide')

        # ── Unité ─────────────────────────────────────────────────────────
        unit = normalized.get('unit', '').strip()
        if not unit:
            row_errors.append('unit requis')

        # ── Fréquence (secondes canoniques, minutes converties si fournies) ─
        frequency = _resolve_frequency_seconds(normalized, row_errors)

        # ── Seuils ────────────────────────────────────────────────────────
        threshold_min = _parse_float(
            normalized.get('threshold_min'), 'threshold_min', row_errors
        )
        threshold_max = _parse_float(
            normalized.get('threshold_max'), 'threshold_max', row_errors
        )
        if (
            threshold_min is not None
            and threshold_max is not None
            and threshold_min >= threshold_max
        ):
            row_errors.append(
                'Le seuil minimum doit être inférieur au seuil maximum'
            )

        # ── Statut actif ──────────────────────────────────────────────────
        active = _parse_bool(normalized.get('active'), row_errors)

        if row_errors:
            errors.append({'row': index, 'message': ' ; '.join(row_errors)})
            rejected += 1
            continue

        name = normalized.get('name', '').strip() or sensor_id
        description = normalized.get('description', '').strip()

        seen_ids.add(sensor_id)
        valid_rows.append({
            'sensor_id': sensor_id,
            'name': name,
            'machine': machine,
            'machine_identifiant': machine_identifiant,
            'type': sensor_type,
            'unit': unit,
            'frequency_seconds': frequency,
            'threshold_min': threshold_min,
            'threshold_max': threshold_max,
            'active': active,
            'description': description,
        })

        if len(preview_items) < PREVIEW_LIMIT:
            preview_items.append({
                'sensor_id': sensor_id,
                'name': name,
                'machine_identifiant': machine_identifiant,
                'type': sensor_type,
                'unit': unit,
                'frequency_seconds': frequency,
                'threshold_min': threshold_min,
                'threshold_max': threshold_max,
                'active': active,
            })

        imported += 1

    if not dry_run and valid_rows:
        with transaction.atomic():
            for item in valid_rows:
                Sensor.objects.create(
                    identifiant=item['sensor_id'],
                    nom=item['name'],
                    type_capteur=item['type'],
                    machine=item['machine'],
                    unite=item['unit'],
                    frequence_mesure=item['frequency_seconds'],
                    seuil_min=item['threshold_min'],
                    seuil_max=item['threshold_max'],
                    actif=item['active'],
                    description=item['description'],
                )

    return {
        'imported': imported,
        'rejected': rejected,
        'duplicates': duplicates,
        'errors': errors,
        'total_rows': imported + rejected + duplicates,
        'preview_items': preview_items,
        # Colonnes canoniques détectées (diagnostic en cas d'en-tête inattendu).
        'columns': columns,
    }
