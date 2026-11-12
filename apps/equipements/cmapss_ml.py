"""CMAPSS remaining-useful-life training and inference helpers.

The model is for NASA's simulated turbofan benchmark only. Its 21 sensor channels
do not map automatically to the generic SmartFactory machine sensors.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from django.conf import settings

WINDOW_SIZE = 30
RUL_CAP = 125
INPUT_FEATURES = 24  # 3 operating settings + 21 sensor readings
DATASETS = ('FD001', 'FD002', 'FD003', 'FD004')


def model_path() -> Path:
    configured = getattr(settings, 'CMAPSS_MODEL_PATH', '')
    return Path(configured) if configured else Path(settings.BASE_DIR) / 'ml' / 'artifacts' / 'cmapss_rul.joblib'


def _make_features(history, cycle):
    """Fixed-size features: current values, rolling stats and recent trends."""
    import numpy as np
    rows = np.asarray(history, dtype=np.float32)
    if rows.ndim != 2 or rows.shape[1] != INPUT_FEATURES or rows.shape[0] == 0:
        raise ValueError(f'Chaque moteur doit fournir au moins une ligne de {INPUT_FEATURES} valeurs.')
    rows = rows[-WINDOW_SIZE:]
    if len(rows) < WINDOW_SIZE:
        rows = np.vstack((np.repeat(rows[:1], WINDOW_SIZE - len(rows), axis=0), rows))

    parts = [rows[-1]]
    for width in (5, 15):
        recent = rows[-width:]
        parts.extend((recent.mean(axis=0), recent.std(axis=0)))
        centered_x = np.arange(width, dtype=np.float32) - (width - 1) / 2
        slope = (centered_x[:, None] * recent).sum(axis=0) / max(float((centered_x ** 2).sum()), 1.0)
        parts.append(slope)
    parts.append(np.asarray([float(cycle)], dtype=np.float32))
    return np.concatenate(parts).astype(np.float32, copy=False)


def _read_cmapss_file(path):
    import numpy as np
    engines = {}
    with open(path, 'r', encoding='utf-8') as source:
        for line_number, line in enumerate(source, start=1):
            values = line.split()
            if not values:
                continue
            if len(values) != 26:
                raise ValueError(f'{path.name}, ligne {line_number}: 26 colonnes attendues, {len(values)} trouvées.')
            try:
                unit, cycle = int(float(values[0])), int(float(values[1]))
                features = np.asarray([float(value) for value in values[2:]], dtype=np.float32)
            except ValueError as exc:
                raise ValueError(f'{path.name}, ligne {line_number}: valeur non numérique.') from exc
            if not np.isfinite(features).all():
                raise ValueError(f'{path.name}, ligne {line_number}: valeur non finie.')
            engines.setdefault(unit, []).append((cycle, features))
    return {unit: sorted(rows, key=lambda item: item[0]) for unit, rows in engines.items()}


def _load_train_examples(data_dir, datasets=DATASETS):
    import numpy as np
    x_values, y_values, groups = [], [], []
    for dataset in datasets:
        engines = _read_cmapss_file(Path(data_dir) / f'train_{dataset}.txt')
        for unit, samples in engines.items():
            final_cycle = samples[-1][0]
            history = []
            for cycle, values in samples:
                history.append(values)
                x_values.append(_make_features(history, cycle))
                y_values.append(min(final_cycle - cycle, RUL_CAP))
                groups.append(f'{dataset}-{unit}')
    return np.vstack(x_values), np.asarray(y_values, dtype=np.float32), np.asarray(groups)


def _load_test_examples(data_dir, dataset):
    import numpy as np
    engines = _read_cmapss_file(Path(data_dir) / f'test_{dataset}.txt')
    rul_path = Path(data_dir) / f'RUL_{dataset}.txt'
    expected_rul = np.asarray([float(line) for line in rul_path.read_text(encoding='utf-8').split()], dtype=np.float32)
    ordered_units = sorted(engines)
    if len(expected_rul) != len(ordered_units):
        raise ValueError(f'{rul_path.name}: {len(expected_rul)} RUL, mais {len(ordered_units)} moteurs de test.')
    x_values, y_values = [], []
    for unit, true_rul in zip(ordered_units, expected_rul):
        samples = engines[unit]
        cycle, _ = samples[-1]
        x_values.append(_make_features([values for _, values in samples], cycle))
        y_values.append(float(true_rul))
    return np.vstack(x_values), expected_rul, ordered_units


def _metrics(actual, predicted):
    import numpy as np
    error = predicted - actual
    score_terms = np.where(error < 0, np.expm1(-error / 13.0), np.expm1(error / 10.0))
    return {
        'engines': int(len(actual)),
        'mae_cycles': round(float(np.mean(np.abs(error))), 3),
        'rmse_cycles': round(float(np.sqrt(np.mean(error ** 2))), 3),
        'nasa_score': round(float(np.sum(score_terms)), 3),
        'evaluation_target': 'RUL capped at 125 cycles',
    }


def train_model(data_dir, output_path, datasets=DATASETS):
    """Train, validate on held-out engines, evaluate official test sets, save."""
    import joblib
    import numpy as np
    import sklearn
    from sklearn.ensemble import HistGradientBoostingRegressor

    data_dir = Path(data_dir)
    output_path = Path(output_path)
    x_train, y_train, groups = _load_train_examples(data_dir, datasets)
    validation_mask = np.asarray([int(group.rsplit('-', 1)[1]) % 5 == 0 for group in groups])
    if not validation_mask.any() or validation_mask.all():
        raise ValueError('Impossible de séparer les moteurs pour la validation.')

    def build_model():
        return HistGradientBoostingRegressor(
            loss='squared_error', learning_rate=0.08, max_iter=180,
            max_leaf_nodes=25, min_samples_leaf=35, l2_regularization=1.0,
            early_stopping=False, random_state=42,
        )

    validation_model = build_model()
    validation_model.fit(x_train[~validation_mask], y_train[~validation_mask])
    val_features, val_actual_values = [], []
    for dataset in datasets:
        engines = _read_cmapss_file(data_dir / f'train_{dataset}.txt')
        for unit, samples in engines.items():
            if unit % 5 != 0:
                continue
            cutoff = max(1, int(len(samples) * 0.75))
            observed = samples[:cutoff]
            cycle = observed[-1][0]
            val_features.append(_make_features([value for _, value in observed], cycle))
            val_actual_values.append(min(samples[-1][0] - cycle, RUL_CAP))
    val_actual = np.asarray(val_actual_values, dtype=np.float32)
    val_predicted = np.clip(validation_model.predict(np.vstack(val_features)), 0, RUL_CAP)

    final_model = build_model()
    final_model.fit(x_train, y_train)
    test_metrics = {}
    for dataset in datasets:
        test_x, true_rul, _ = _load_test_examples(data_dir, dataset)
        predicted = np.clip(final_model.predict(test_x), 0, RUL_CAP)
        test_metrics[dataset] = _metrics(np.minimum(true_rul, RUL_CAP), predicted)

    report = {
        'model': 'HistGradientBoostingRegressor',
        'scikit_learn_version': sklearn.__version__,
        'source': 'NASA C-MAPSS turbofan degradation simulation',
        'datasets': list(datasets),
        'training_engines': int(len(np.unique(groups))),
        'training_rows': int(len(y_train)),
        'feature_count': int(x_train.shape[1]),
        'window_size': WINDOW_SIZE,
        'rul_cap_cycles': RUL_CAP,
        'validation': _metrics(val_actual, val_predicted),
        'official_test': test_metrics,
        'limitations': 'Simulation turbofan C-MAPSS; not calibrated for SmartFactory equipment or visual inspection.',
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump({'model': final_model, 'metadata': report}, output_path, compress=3)
    report_path = output_path.with_name('cmapss_training_report.json')
    import json
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding='utf-8')
    return report


@lru_cache(maxsize=2)
def _load_artifact_cached(path, modified_ns):
    import joblib
    return joblib.load(path)


def load_artifact():
    path = model_path()
    if not path.is_file():
        return None
    return _load_artifact_cached(str(path), path.stat().st_mtime_ns)


def artifact_status():
    path = model_path()
    try:
        artifact = load_artifact()
        error = None
    except ImportError:
        artifact = None
        error = 'Installez les dépendances du modèle avec pip install -r requirements-ml.txt.'
    return {
        'ready': artifact is not None,
        'model_name': artifact['metadata']['model'] if artifact else 'HistGradientBoostingRegressor',
        'metadata': artifact['metadata'] if artifact else None,
        'model_path': str(path),
        'dataset_description': 'NASA C-MAPSS: données de dégradation simulées de moteurs turbofan.',
        'detail': error or (None if artifact else 'Entraînez le modèle avec ml/train_cmapss.py.'),
    }


def predict_rul(history, cycle):
    import numpy as np
    artifact = load_artifact()
    if artifact is None:
        raise FileNotFoundError('Modèle CMAPSS absent. Exécutez le script ml/train_cmapss.py.')
    features = _make_features(history, cycle).reshape(1, -1)
    prediction = float(np.clip(artifact['model'].predict(features)[0], 0, RUL_CAP))
    return {
        'predicted_rul_cycles': round(prediction, 1),
        'health_state': 'CRITIQUE' if prediction <= 30 else 'DEGRADE' if prediction <= 80 else 'NORMAL',
        'cycle': int(cycle),
        'window_size': WINDOW_SIZE,
        'model': artifact['metadata']['model'],
        'dataset': 'NASA C-MAPSS (simulation turbofan)',
        'warning': 'Démonstration de recherche. Cette estimation n’est pas calibrée aux machines de l’usine.',
    }
