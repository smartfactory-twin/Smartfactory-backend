"""Train and report the MetroPT-3 benchmark model.

PowerShell: .\.venv\Scripts\python.exe ml\train_metropt.py
"""
import json
import sys
from pathlib import Path

backend_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(backend_root))

from apps.equipements.metropt_ml import train_metropt_model

report = train_metropt_model()
print(json.dumps(report, indent=2, ensure_ascii=False))
print(f"\nModèle enregistré : {backend_root / 'ml' / 'artifacts' / 'metropt3_anomaly_detector.joblib'}")
