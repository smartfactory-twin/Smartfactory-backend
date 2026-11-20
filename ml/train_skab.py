"""Train and evaluate the SKAB anomaly benchmark.

PowerShell (from Smartfactory-backend):
  .\.venv\Scripts\python.exe ml\train_skab.py
"""
import argparse
import json

from apps.equipements.skab_ml import ARTIFACT_PATH, DATA_DIR, train_skab_model


def main():
    parser = argparse.ArgumentParser(description='Entraîne et évalue les modèles du benchmark SKAB.')
    parser.add_argument('--data-dir', default=str(DATA_DIR), help='Dossier SKAB contenant data/ ou directement les CSV.')
    parser.add_argument('--artifact', default=str(ARTIFACT_PATH), help='Chemin de sortie du fichier joblib.')
    parser.add_argument('--seed', type=int, default=42, help='Graine du découpage et des modèles.')
    args = parser.parse_args()
    report = train_skab_model(args.data_dir, args.artifact, args.seed)
    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == '__main__':
    main()
