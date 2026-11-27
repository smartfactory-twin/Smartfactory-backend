from __future__ import annotations

import csv
import json
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[2]
DATA_PATH = BASE_DIR / 'ml' / 'data' / 'metropt3' / 'Group_14_Clean_Data.csv'
MODEL_PATH = BASE_DIR / 'ml' / 'artifacts' / 'metropt3_anomaly_detector.joblib'
REPORT_PATH = MODEL_PATH.with_name('metropt3_training_report.json')
FAILURE_WINDOWS = (
    ('#1', '2020-04-18 00:00:00', '2020-04-18 23:59:59'),
    ('#2', '2020-05-29 23:30:00', '2020-05-30 06:00:00'),
    ('#3', '2020-06-05 10:00:00', '2020-06-07 14:30:00'),
    ('#4', '2020-07-15 14:30:00', '2020-07-15 19:00:00'),
)


def train_metropt_model(data_path=DATA_PATH, output_path=MODEL_PATH):
    import numpy as np
    import joblib
    from sklearn.ensemble import IsolationForest
    from sklearn.impute import SimpleImputer
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import RobustScaler

    data_path, output_path = Path(data_path), Path(output_path)
    if not data_path.is_file():
        raise FileNotFoundError(f'CSV MetroPT-3 introuvable : {data_path}')

    rows = []
    with data_path.open(newline='', encoding='utf-8-sig') as source:
        reader = csv.DictReader(source)
        fields = reader.fieldnames or []
        if 'timestamp' not in fields:
            raise ValueError('Le CSV doit contenir la colonne timestamp.')
        feature_columns = [name for name in fields if name not in ('', 'timestamp', 'status')]
        if not feature_columns:
            raise ValueError('Aucune colonne capteur trouvée dans le CSV.')
        for line_number, row in enumerate(reader, start=2):
            try:
                timestamp = row['timestamp'].strip()
                values = [float(row[name]) if row[name].strip() else np.nan for name in feature_columns]
            except (AttributeError, TypeError, ValueError) as exc:
                raise ValueError(f'Ligne {line_number} : date ou mesure invalide.') from exc
            rows.append((timestamp, values))

    rows.sort(key=lambda item: item[0])
    if len(rows) < 20:
        raise ValueError('Le CSV doit contenir au moins 20 mesures.')
    calibration_start, test_start = '2020-03-01 00:00:00', '2020-04-01 00:00:00'
    train_rows = [row for row in rows if row[0] < calibration_start]
    calibration_rows = [row for row in rows if calibration_start <= row[0] < test_start]
    test_rows = [row for row in rows if row[0] >= test_start]
    if len(train_rows) < 100 or len(calibration_rows) < 100 or not test_rows:
        raise ValueError('Le CSV doit contenir au moins 100 relevés en février, 100 en mars et des relevés après mars 2020.')

    x_train = np.asarray([row[1] for row in train_rows], dtype=np.float32)
    x_test = np.asarray([row[1] for row in test_rows], dtype=np.float32)
    model = make_pipeline(
        SimpleImputer(strategy='median'),
        RobustScaler(),
        IsolationForest(n_estimators=200, contamination='auto', random_state=42, n_jobs=-1),
    )
    model.fit(x_train)
    calibration_scores = model.score_samples(np.asarray([row[1] for row in calibration_rows], dtype=np.float32))
    # Compromise point for the benchmark: target 5% flagged reference samples
    # in the normal-only calibration month; report the measured test FPR too.
    calibration_percentile = 5
    threshold = float(np.quantile(calibration_scores, calibration_percentile / 100))
    predictions = model.score_samples(x_test) < threshold
    from datetime import datetime
    test_times = [datetime.fromisoformat(row[0]) for row in test_rows]
    labels_test = np.asarray([
        any(datetime.fromisoformat(start) <= timestamp <= datetime.fromisoformat(end)
            for _, start, end in FAILURE_WINDOWS)
        for timestamp in test_times
    ], dtype=bool)
    true_positive = int(np.logical_and(predictions, labels_test).sum())
    false_positive = int(np.logical_and(predictions, ~labels_test).sum())
    false_negative = int(np.logical_and(~predictions, labels_test).sum())
    normal_count = int((~labels_test).sum())
    precision = true_positive / max(true_positive + false_positive, 1)
    recall = true_positive / max(true_positive + false_negative, 1)
    f1 = 2 * precision * recall / max(precision + recall, 1e-12)
    events = []
    for event_id, start, end in FAILURE_WINDOWS:
        in_event = np.asarray([
            datetime.fromisoformat(start) <= timestamp <= datetime.fromisoformat(end)
            for timestamp in test_times
        ], dtype=bool)
        event_count = int(in_event.sum())
        detected_count = int(np.logical_and(in_event, predictions).sum())
        events.append({
            'event': event_id, 'start': start, 'end': end, 'rows': event_count,
            'anomalies_detected': detected_count,
            'detection_rate': round(detected_count / event_count, 4) if event_count else None,
        })
    report = {
        'model': 'IsolationForest',
        'task': 'détection non supervisée d’anomalies, évaluée sur les fenêtres de fuite publiées',
        'source': 'MetroPT-3 · dérivé nettoyé Group 14',
        'source_url': 'https://github.com/harveyphm/MetroPT-3-Anomaly-Detection',
        'upstream_dataset_url': 'https://archive.ics.uci.edu/dataset/791/metropt+3+dataset',
        'dataset_context': 'Télémétrie réelle d’un compresseur ferroviaire (Metro do Porto), distincte des machines de l’usine SmartFactory.',
        'evaluation_method': 'status ignoré. Référence entraînée sur février 2020; seuil calibré au 5e percentile sur mars; test évalué contre les quatre fenêtres de fuite publiées par UCI.',
        'feature_columns': feature_columns,
        'feature_count': len(feature_columns),
        'rows': len(rows),
        'training_period_rule': 'Février 2020 uniquement, sans utiliser le champ status.',
        'calibration_period_rule': 'Mars 2020, période sans panne signalée. Seuil au 5e percentile des scores afin de privilégier le rappel; le taux réel de fausses alertes est mesuré sur le test.',
        'test_period_rule': 'Tous les relevés à partir du 1er avril 2020; les fenêtres de panne UCI servent uniquement à évaluer.',
        'calibration_rows': len(calibration_rows),
        'calibration_period': {'start': calibration_rows[0][0], 'end': calibration_rows[-1][0]},
        'threshold_score': round(threshold, 6),
        'threshold_calibration_percentile': calibration_percentile,
        'train_rows': len(train_rows),
        'test_rows': len(test_rows),
        'train_period': {'start': train_rows[0][0], 'end': train_rows[-1][0]},
        'test_period': {'start': test_rows[0][0], 'end': test_rows[-1][0]},
        'evaluation_events': events,
        'metrics': {
            'precision': round(precision, 4),
            'recall': round(recall, 4),
            'f1': round(f1, 4),
            'false_positive_rate': round(false_positive / max(normal_count, 1), 4),
            'true_positive_rows': true_positive,
            'false_positive_rows': false_positive,
            'false_negative_rows': false_negative,
            'failure_window_rows': int(labels_test.sum()),
            'normal_rows': normal_count,
            'failure_window_share': round(float(labels_test.mean()), 4),
        },
        'limitations': 'Évaluation sur un dérivé nettoyé communautaire plus petit que le fichier UCI intégral; les événements publiés servent de vérité terrain par période, pas de diagnostic détaillé. Ce benchmark ne valide pas les capteurs des machines SmartFactory.',
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump({'model': model, 'metadata': report}, output_path, compress=3)
    output_path.with_name(REPORT_PATH.name).write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding='utf-8')
    return report


def metropt_artifact_status():
    if not MODEL_PATH.is_file():
        return {'ready': False, 'model_name': 'IsolationForest', 'metadata': None, 'detail': 'Entraînez le benchmark avec ml/train_metropt.py.'}
    try:
        import joblib
        artifact = joblib.load(MODEL_PATH)
        return {'ready': True, 'model_name': artifact['metadata']['model'], 'metadata': artifact['metadata'], 'detail': None}
    except (ImportError, OSError, KeyError, ValueError) as error:
        return {'ready': False, 'model_name': 'IsolationForest', 'metadata': None, 'detail': f'Artefact illisible : {error}'}
