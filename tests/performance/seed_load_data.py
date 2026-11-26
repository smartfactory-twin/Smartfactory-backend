"""Create an idempotent 50-machine / 500-sensor load fixture.

Use only with an explicitly named, dedicated database. This script never
deletes data and only creates rows with the PERF- prefix.
"""
import argparse
import os
from pathlib import Path
import sys


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--settings', default='core.settings_load')
    args = parser.parse_args()

    if os.getenv('PERFORMANCE_TEST_CONFIRM') != 'YES':
        raise SystemExit('Refus: définir PERFORMANCE_TEST_CONFIRM=YES après vérification de la base dédiée.')

    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', args.settings)
    import django
    django.setup()

    from django.conf import settings
    from apps.equipements.models import LigneProduction, Machine, Sensor, Usine, Zone

    db_name = str(settings.DATABASES['default'].get('NAME', ''))
    if not any(marker in db_name.lower() for marker in ('load', 'performance', 'perf_test')):
        raise SystemExit(f"Refus : DB_NAME={db_name!r} ne désigne pas une base load/performance dédiée.")

    usine, _ = Usine.objects.get_or_create(
        nom='PERF-Usine', defaults={'description': 'Fixture de test de charge; données jetables.'},
    )
    zone, _ = Zone.objects.get_or_create(
        nom='PERF-Zone', usine=usine, defaults={'description': 'Fixture de test de charge.'},
    )
    ligne, _ = LigneProduction.objects.get_or_create(
        nom='PERF-Ligne', zone=zone, defaults={'description': 'Fixture de test de charge.'},
    )

    machines_created = 0
    sensors_created = 0
    for machine_index in range(1, 51):
        machine, created = Machine.objects.get_or_create(
            identifiant_interne=f'PERF-MACHINE-{machine_index:03d}',
            defaults={
                'nom': f'PERF Machine {machine_index:03d}',
                'type_equipement': Machine.TypeEquipement.AUTRE,
                'statut': Machine.Statut.NORMAL,
                'ligne_production': ligne,
                'description': 'Fixture de test de charge; ne pas utiliser en production.',
            },
        )
        machines_created += int(created)

        for sensor_index in range(1, 11):
            _, created = Sensor.objects.get_or_create(
                identifiant=f'PERF-SENSOR-{machine_index:03d}-{sensor_index:02d}',
                defaults={
                    'nom': f'PERF Capteur {machine_index:03d}-{sensor_index:02d}',
                    'type_capteur': Sensor.SensorType.TEMPERATURE,
                    'machine': machine,
                    'unite': '°C',
                    'frequence_mesure': 60,
                    'seuil_min': 0,
                    'seuil_max': 100,
                    'sensor_role': Sensor.SensorRole.OTHER,
                    'criticality': Sensor.Criticality.LOW,
                    'is_ai_eligible': False,
                    'actif': True,
                    'description': 'Fixture de test de charge; données synthétiques.',
                },
            )
            sensors_created += int(created)

    total_machines = Machine.objects.filter(identifiant_interne__startswith='PERF-MACHINE-').count()
    total_sensors = Sensor.objects.filter(identifiant__startswith='PERF-SENSOR-').count()
    print({
        'database': db_name,
        'machines_fixture': total_machines,
        'sensors_fixture': total_sensors,
        'machines_created_this_run': machines_created,
        'sensors_created_this_run': sensors_created,
        'deleted': 0,
    })


if __name__ == '__main__':
    main()
