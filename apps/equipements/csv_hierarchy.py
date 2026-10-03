import csv
import io
from datetime import datetime
from django.utils.dateparse import parse_date
from django.db import transaction
from django.http import HttpResponse
from rest_framework import status
from rest_framework.response import Response

from .models import Usine, Zone, LigneProduction, Machine, Composant

CSV_COLUMNS = [
    'usine_nom', 'usine_adresse', 'usine_description',
    'zone_nom', 'zone_description',
    'ligne_nom', 'ligne_description',
    'machine_identifiant', 'machine_nom', 'machine_numero_serie',
    'machine_marque', 'machine_modele', 'machine_date_installation',
    'machine_statut', 'machine_description',
    'composant_nom', 'composant_numero_piece', 'composant_description'
]

HEADER_ALIASES = {
    # Usine
    'usine_nom': 'usine_nom',
    'usine': 'usine_nom',
    'nom_usine': 'usine_nom',
    'usine_adresse': 'usine_adresse',
    'adresse_usine': 'usine_adresse',
    'adresse': 'usine_adresse',
    'usine_description': 'usine_description',
    'description_usine': 'usine_description',

    # Zone
    'zone_nom': 'zone_nom',
    'zone': 'zone_nom',
    'nom_zone': 'zone_nom',
    'zone_description': 'zone_description',
    'description_zone': 'zone_description',

    # Ligne
    'ligne_nom': 'ligne_nom',
    'ligne': 'ligne_nom',
    'nom_ligne': 'ligne_nom',
    'ligne_production': 'ligne_nom',
    'ligne_production_nom': 'ligne_nom',
    'ligne_description': 'ligne_description',
    'description_ligne': 'ligne_description',

    # Machine
    'machine_identifiant': 'machine_identifiant',
    'identifiant_interne': 'machine_identifiant',
    'identifiant_machine': 'machine_identifiant',
    'machine_id': 'machine_identifiant',
    'machine_nom': 'machine_nom',
    'machine': 'machine_nom',
    'nom_machine': 'machine_nom',
    'machine_numero_serie': 'machine_numero_serie',
    'numero_serie': 'machine_numero_serie',
    'machine_marque': 'machine_marque',
    'marque': 'machine_marque',
    'machine_modele': 'machine_modele',
    'modele': 'machine_modele',
    'machine_date_installation': 'machine_date_installation',
    'date_installation': 'machine_date_installation',
    'machine_statut': 'machine_statut',
    'statut': 'machine_statut',
    'machine_description': 'machine_description',
    'description_machine': 'machine_description',

    # Composant
    'composant_nom': 'composant_nom',
    'composant': 'composant_nom',
    'nom_composant': 'composant_nom',
    'composant_numero_piece': 'composant_numero_piece',
    'numero_piece': 'composant_numero_piece',
    'composant_description': 'composant_description',
    'description_composant': 'composant_description',
}

VALID_STATUTS = [s[0] for s in Machine.Statut.choices]


def parse_csv_file(file_obj):
    """Lit et décode un fichier CSV avec détection d'encodage et de délimiteur."""
    raw = file_obj.read()
    content = None
    for enc in ('utf-8-sig', 'utf-8', 'latin1', 'cp1252'):
        try:
            content = raw.decode(enc)
            break
        except (UnicodeDecodeError, LookupError):
            continue
    if content is None:
        content = raw.decode('utf-8', errors='replace')

    # Detect delimiter
    first_line = content.split('\n')[0] if content else ''
    delimiter = ';' if ';' in first_line and ',' not in first_line else ','

    reader = csv.DictReader(io.StringIO(content), delimiter=delimiter)
    return reader


def normalize_row(raw_row):
    """Normalise les noms de colonnes et les valeurs d'une ligne CSV."""
    normalized = {}
    for k, v in raw_row.items():
        if k is None:
            continue
        clean_key = k.strip().lower().replace(' ', '_').replace('-', '_')
        target_key = HEADER_ALIASES.get(clean_key, clean_key)
        val = v.strip() if isinstance(v, str) else ('' if v is None else str(v).strip())
        normalized[target_key] = val
    return normalized


def validate_and_parse_hierarchy_csv(file_obj):
    """
    Parse et valide le CSV de hiérarchie complète.
    Retourne (valid_rows, invalid_rows, errors, summary, preview_items).
    """
    reader = parse_csv_file(file_obj)
    valid_rows = []
    invalid_rows = []
    errors = []

    unique_usines = set()
    unique_zones = set()
    unique_lignes = set()
    unique_machines = set()
    composants_count = 0

    preview_items = []

    for i, raw_row in enumerate(reader, start=2):
        normalized = normalize_row(raw_row)
        # Skip completely empty rows
        if not any(normalized.values()):
            continue

        row_errors = []
        usine_nom = normalized.get('usine_nom', '')
        if not usine_nom:
            row_errors.append("Le nom de l'usine est obligatoire (colonne 'usine_nom').")

        zone_nom = normalized.get('zone_nom', '')
        ligne_nom = normalized.get('ligne_nom', '')

        if ligne_nom and not zone_nom:
            row_errors.append(f"Une zone doit être spécifiée pour la ligne '{ligne_nom}'.")

        machine_identifiant = normalized.get('machine_identifiant', '')
        machine_nom = normalized.get('machine_nom', '')
        machine_statut = normalized.get('machine_statut', '').upper()
        machine_date = normalized.get('machine_date_installation', '')

        # Si des informations machine sont données
        has_machine_fields = bool(
            machine_identifiant or machine_nom or
            normalized.get('machine_numero_serie') or normalized.get('machine_marque') or
            normalized.get('machine_modele') or machine_date or machine_statut or
            normalized.get('machine_description')
        )

        if has_machine_fields:
            if not machine_identifiant:
                row_errors.append("L'identifiant interne de la machine est obligatoire (colonne 'machine_identifiant').")
            if not machine_nom:
                # Use machine_identifiant as default name if missing
                normalized['machine_nom'] = machine_identifiant

            if not zone_nom or not ligne_nom:
                row_errors.append("Une zone et une ligne de production sont obligatoires pour associer une machine.")

            if machine_statut and machine_statut not in VALID_STATUTS:
                row_errors.append(f"Statut machine '{machine_statut}' invalide. Valeurs acceptées: {', '.join(VALID_STATUTS)}.")

            if machine_date:
                parsed_d = parse_date(machine_date)
                if not parsed_d:
                    row_errors.append(f"Date d'installation '{machine_date}' invalide. Format attendu: YYYY-MM-DD.")
                else:
                    normalized['_parsed_date'] = parsed_d

        composant_nom = normalized.get('composant_nom', '')
        composant_piece = normalized.get('composant_numero_piece', '')
        has_composant_fields = bool(composant_nom or composant_piece or normalized.get('composant_description'))

        if has_composant_fields:
            if not composant_nom:
                row_errors.append("Le nom du composant est obligatoire (colonne 'composant_nom').")
            if not machine_identifiant:
                row_errors.append("Un composant doit être rattaché à une machine valide dans la même ligne.")

        if row_errors:
            for err in row_errors:
                errors.append({'row': i, 'message': err})
            invalid_rows.append({'row': i, 'data': normalized, 'errors': row_errors})
        else:
            valid_rows.append(normalized)
            unique_usines.add(usine_nom)
            if zone_nom:
                unique_zones.add((usine_nom, zone_nom))
            if ligne_nom and zone_nom:
                unique_lignes.add((usine_nom, zone_nom, ligne_nom))
            if machine_identifiant:
                unique_machines.add(machine_identifiant)
            if composant_nom and machine_identifiant:
                composants_count += 1

            if len(preview_items) < 20:
                preview_items.append({
                    'row': i,
                    'usine': usine_nom,
                    'zone': zone_nom,
                    'ligne': ligne_nom,
                    'machine_identifiant': machine_identifiant,
                    'machine_nom': normalized.get('machine_nom', ''),
                    'composant_nom': composant_nom,
                })

    summary = {
        'usines_count': len(unique_usines),
        'zones_count': len(unique_zones),
        'lignes_count': len(unique_lignes),
        'machines_count': len(unique_machines),
        'composants_count': composants_count,
    }

    return {
        'valid_rows': valid_rows,
        'invalid_rows': invalid_rows,
        'errors': errors,
        'total_rows_count': len(valid_rows) + len(invalid_rows),
        'valid_rows_count': len(valid_rows),
        'invalid_rows_count': len(invalid_rows),
        'summary': summary,
        'preview_items': preview_items,
    }


def execute_hierarchy_import(valid_rows):
    """
    Exécute l'insertion / mise à jour de la hiérarchie dans la base de données.
    Réutilise les Usines, Zones, Lignes et Machines existantes.
    """
    stats = {
        'usines_created': 0,
        'usines_reused': 0,
        'zones_created': 0,
        'zones_reused': 0,
        'lignes_created': 0,
        'lignes_reused': 0,
        'machines_created': 0,
        'machines_updated': 0,
        'composants_created': 0,
        'composants_reused': 0,
    }

    cache_usines = {}
    cache_zones = {}
    cache_lignes = {}

    with transaction.atomic():
        for row in valid_rows:
            usine_nom = row['usine_nom']
            usine_adresse = row.get('usine_adresse', '')
            usine_desc = row.get('usine_description', '')

            # ── 1. Usine ──────────────────────────────────────────────────────
            if usine_nom not in cache_usines:
                usine, created = Usine.objects.get_or_create(
                    nom=usine_nom,
                    defaults={'adresse': usine_adresse, 'description': usine_desc}
                )
                if created:
                    stats['usines_created'] += 1
                else:
                    stats['usines_reused'] += 1
                    updated = False
                    if usine_adresse and not usine.adresse:
                        usine.adresse = usine_adresse
                        updated = True
                    if usine_desc and not usine.description:
                        usine.description = usine_desc
                        updated = True
                    if updated:
                        usine.save()
                cache_usines[usine_nom] = usine
            else:
                usine = cache_usines[usine_nom]

            # ── 2. Zone ───────────────────────────────────────────────────────
            zone_nom = row.get('zone_nom', '')
            zone_desc = row.get('zone_description', '')
            zone = None
            if zone_nom:
                zone_key = (usine.id, zone_nom)
                if zone_key not in cache_zones:
                    zone, created = Zone.objects.get_or_create(
                        nom=zone_nom,
                        usine=usine,
                        defaults={'description': zone_desc}
                    )
                    if created:
                        stats['zones_created'] += 1
                    else:
                        stats['zones_reused'] += 1
                        if zone_desc and not zone.description:
                            zone.description = zone_desc
                            zone.save()
                    cache_zones[zone_key] = zone
                else:
                    zone = cache_zones[zone_key]

            # ── 3. Ligne ──────────────────────────────────────────────────────
            ligne_nom = row.get('ligne_nom', '')
            ligne_desc = row.get('ligne_description', '')
            ligne = None
            if ligne_nom and zone:
                ligne_key = (zone.id, ligne_nom)
                if ligne_key not in cache_lignes:
                    ligne, created = LigneProduction.objects.get_or_create(
                        nom=ligne_nom,
                        zone=zone,
                        defaults={'description': ligne_desc}
                    )
                    if created:
                        stats['lignes_created'] += 1
                    else:
                        stats['lignes_reused'] += 1
                        if ligne_desc and not ligne.description:
                            ligne.description = ligne_desc
                            ligne.save()
                    cache_lignes[ligne_key] = ligne
                else:
                    ligne = cache_lignes[ligne_key]

            # ── 4. Machine ────────────────────────────────────────────────────
            machine_identifiant = row.get('machine_identifiant', '')
            machine = None
            if machine_identifiant:
                machine_nom = row.get('machine_nom') or machine_identifiant
                machine_serie = row.get('machine_numero_serie', '')
                machine_marque = row.get('machine_marque', '')
                machine_modele = row.get('machine_modele', '')
                machine_statut = row.get('machine_statut', '').upper() or Machine.Statut.NORMAL
                machine_desc = row.get('machine_description', '')
                parsed_date = row.get('_parsed_date')

                existing = Machine.objects.filter(identifiant_interne=machine_identifiant).first()
                if existing:
                    # Update fields if provided
                    if machine_nom:
                        existing.nom = machine_nom
                    if machine_serie:
                        existing.numero_serie = machine_serie
                    if machine_marque:
                        existing.marque = machine_marque
                    if machine_modele:
                        existing.modele = machine_modele
                    if parsed_date:
                        existing.date_installation = parsed_date
                    if machine_statut and machine_statut in VALID_STATUTS:
                        existing.statut = machine_statut
                    if machine_desc:
                        existing.description = machine_desc
                    if ligne:
                        existing.ligne_production = ligne
                    existing.save()
                    machine = existing
                    stats['machines_updated'] += 1
                else:
                    machine = Machine.objects.create(
                        identifiant_interne=machine_identifiant,
                        nom=machine_nom,
                        numero_serie=machine_serie,
                        marque=machine_marque,
                        modele=machine_modele,
                        date_installation=parsed_date,
                        statut=machine_statut if machine_statut in VALID_STATUTS else Machine.Statut.NORMAL,
                        description=machine_desc,
                        ligne_production=ligne
                    )
                    stats['machines_created'] += 1

            # ── 5. Composant ──────────────────────────────────────────────────
            composant_nom = row.get('composant_nom', '')
            if composant_nom and machine:
                composant_piece = row.get('composant_numero_piece', '')
                composant_desc = row.get('composant_description', '')

                comp, created = Composant.objects.get_or_create(
                    nom=composant_nom,
                    machine=machine,
                    defaults={
                        'numero_piece': composant_piece,
                        'description': composant_desc
                    }
                )
                if created:
                    stats['composants_created'] += 1
                else:
                    stats['composants_reused'] += 1
                    updated = False
                    if composant_piece and not comp.numero_piece:
                        comp.numero_piece = composant_piece
                        updated = True
                    if composant_desc and not comp.description:
                        comp.description = composant_desc
                        updated = True
                    if updated:
                        comp.save()

    return stats


def export_hierarchy_csv():
    """Génère l'export CSV de la hiérarchie complète des équipements."""
    output = io.StringIO()
    # UTF-8 BOM pour compatibilité Excel
    output.write('\ufeff')
    writer = csv.DictWriter(output, fieldnames=CSV_COLUMNS)
    writer.writeheader()

    usines = Usine.objects.prefetch_related(
        'zones',
        'zones__lignes',
        'zones__lignes__machines',
        'zones__lignes__machines__composants'
    ).all().order_by('nom')

    for usine in usines:
        zones = list(usine.zones.all())
        if not zones:
            writer.writerow({
                'usine_nom': usine.nom,
                'usine_adresse': usine.adresse,
                'usine_description': usine.description,
            })
            continue

        for zone in zones:
            lignes = list(zone.lignes.all())
            if not lignes:
                writer.writerow({
                    'usine_nom': usine.nom,
                    'usine_adresse': usine.adresse,
                    'usine_description': usine.description,
                    'zone_nom': zone.nom,
                    'zone_description': zone.description,
                })
                continue

            for ligne in lignes:
                machines = list(ligne.machines.all())
                if not machines:
                    writer.writerow({
                        'usine_nom': usine.nom,
                        'usine_adresse': usine.adresse,
                        'usine_description': usine.description,
                        'zone_nom': zone.nom,
                        'zone_description': zone.description,
                        'ligne_nom': ligne.nom,
                        'ligne_description': ligne.description,
                    })
                    continue

                for machine in machines:
                    composants = list(machine.composants.all())
                    machine_data = {
                        'usine_nom': usine.nom,
                        'usine_adresse': usine.adresse,
                        'usine_description': usine.description,
                        'zone_nom': zone.nom,
                        'zone_description': zone.description,
                        'ligne_nom': ligne.nom,
                        'ligne_description': ligne.description,
                        'machine_identifiant': machine.identifiant_interne,
                        'machine_nom': machine.nom,
                        'machine_numero_serie': machine.numero_serie,
                        'machine_marque': machine.marque,
                        'machine_modele': machine.modele,
                        'machine_date_installation': str(machine.date_installation) if machine.date_installation else '',
                        'machine_statut': machine.statut,
                        'machine_description': machine.description,
                    }

                    if not composants:
                        writer.writerow(machine_data)
                    else:
                        for comp in composants:
                            row = dict(machine_data)
                            row.update({
                                'composant_nom': comp.nom,
                                'composant_numero_piece': comp.numero_piece,
                                'composant_description': comp.description,
                            })
                            writer.writerow(row)

    response = HttpResponse(output.getvalue(), content_type='text/csv; charset=utf-8')
    response['Content-Disposition'] = 'attachment; filename="smartfactory_hierarchie.csv"'
    return response
