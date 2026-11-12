"""Train the CMAPSS RUL model end to end.

Example (PowerShell):
  .\.venv\Scripts\python.exe ml\train_cmapss.py --data-dir "$env:USERPROFILE\Downloads\CMAPSSData"
"""
import argparse
import json
import os
import sys
from pathlib import Path

def main():
    backend_root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(backend_root))
    import django
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
    django.setup()
    from apps.equipements.cmapss_ml import DATASETS, model_path, train_model

    parser = argparse.ArgumentParser(description='Entraîne et évalue un modèle RUL NASA C-MAPSS.')
    parser.add_argument(
        '--data-dir',
        default=os.path.join(os.path.expanduser('~'), 'Downloads', 'CMAPSSData'),
        help='Dossier contenant train_FD00x, test_FD00x et RUL_FD00x.',
    )
    parser.add_argument('--output', default=str(model_path()), help='Chemin du modèle entraîné .joblib.')
    parser.add_argument('--datasets', nargs='+', choices=DATASETS, default=list(DATASETS))
    args = parser.parse_args()
    report = train_model(args.data_dir, args.output, tuple(args.datasets))
    print(json.dumps(report, indent=2, ensure_ascii=False))
    print(f"\nModèle enregistré : {args.output}")
    print(f"Rapport enregistré : {Path(args.output).with_name('cmapss_training_report.json')}")


if __name__ == '__main__':
    main()
