"""SKAB benchmark training/evaluation pipeline (not wired to the API).

All windows are time based. Experiment CSVs are groups: a file is never split
between train, calibration, validation, and final test.
"""
from __future__ import annotations

import csv
import json
import math
import random
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = BASE_DIR / 'ml' / 'data' / 'SKAB' / 'data'
ARTIFACT_PATH = BASE_DIR / 'ml' / 'artifacts' / 'skab_anomaly_detector.joblib'
REPORT_PATH = ARTIFACT_PATH.with_name('skab_training_report.json')
SEED = 42
WINDOW_SECONDS = 30
TARGET_FALSE_POSITIVE_RATE = 0.05
FOLD_COUNT = 5

SENSOR_COLUMNS = (
    'Accelerometer1RMS', 'Accelerometer2RMS', 'Current', 'Pressure',
    'Temperature', 'Thermocouple', 'Voltage', 'Volume Flow RateRMS',
)
WINDOW_STATS = ('median', 'mad', 'min', 'max', 'last', 'slope_per_second')
FEATURE_NAMES = tuple(
    f'{column}__{stat}' for column in SENSOR_COLUMNS for stat in WINDOW_STATS
)

# SKAB's data README describes the individual `other` experiments. Unknown
# names remain clearly labeled as such instead of receiving an inferred type.
OTHER_SCENARIOS = {
    '1': 'fuite ou ajout de fluide', '2': 'fuite ou ajout de fluide',
    '3': 'fuite ou ajout de fluide', '4': 'fuite ou ajout de fluide',
    '5': 'déséquilibre rotor — brusque', '6': 'déséquilibre rotor — linéaire',
    '7': 'déséquilibre rotor — échelon', '8': 'déséquilibre rotor — impulsion',
    '9': 'déséquilibre rotor — exponentiel', '10': 'augmentation lente du niveau d’eau',
    '11': 'augmentation brusque du niveau d’eau', '12': 'vidange et cavitation',
    '13': 'alimentation diphasique / cavitation', '14': 'eau d’alimentation plus chaude',
}


@dataclass(frozen=True)
class Window:
    file: str
    folder: str
    anomaly_type: str
    timestamp: datetime
    features: tuple[float, ...]
    anomaly: int
    changepoint: int
    all_normal: bool
    observations: int


def _folder(path: str | Path) -> str:
    return Path(path).parent.name


def anomaly_type_for_file(path: str | Path) -> str:
    relative = Path(path)
    folder = relative.parent.name
    if folder == 'valve1':
        return 'fermeture valve entrée'
    if folder == 'valve2':
        return 'fermeture valve sortie'
    if folder == 'other':
        return OTHER_SCENARIOS.get(relative.stem, f'autre expérience #{relative.stem}')
    if folder == 'anomaly-free':
        return 'mode normal'
    return 'type non documenté'


def _allocate_counts(count: int, ratios: dict[str, float]) -> dict[str, int]:
    """Largest-remainder allocation with stable train/calibration/test ties."""
    names = ('train', 'calibration', 'test')
    quotas = {name: count * ratios.get(name, 0.0) for name in names}
    allocated = {name: math.floor(quotas[name]) for name in names}
    remaining = count - sum(allocated.values())
    order = sorted(names, key=lambda name: (-(quotas[name] - allocated[name]), names.index(name)))
    for name in order[:remaining]:
        allocated[name] += 1
    return allocated


def stratified_file_split(
    files: list[str] | tuple[str, ...],
    seed: int = SEED,
    ratios: dict[str, float] | None = None,
) -> dict[str, list[str]]:
    """Split experiment file paths by folder, deterministically and disjointly."""
    ratios = ratios or {'train': 0.6, 'calibration': 0.2, 'test': 0.2}
    if set(ratios) != {'train', 'calibration', 'test'}:
        raise ValueError('Les ratios doivent définir train, calibration et test.')
    if any(value < 0 for value in ratios.values()) or not math.isclose(sum(ratios.values()), 1.0):
        raise ValueError('Les ratios doivent être positifs et leur somme égale à 1.')
    if len(set(files)) != len(files):
        raise ValueError('La liste contient des chemins de fichier en double.')

    by_folder: dict[str, list[str]] = defaultdict(list)
    for file in files:
        by_folder[_folder(file)].append(str(file).replace('\\', '/'))

    result = {'train': [], 'calibration': [], 'test': []}
    rng = random.Random(seed)
    for folder in sorted(by_folder):
        values = sorted(by_folder[folder])
        rng.shuffle(values)
        counts = _allocate_counts(len(values), ratios)
        first = counts['train']
        second = first + counts['calibration']
        result['train'].extend(values[:first])
        result['calibration'].extend(values[first:second])
        result['test'].extend(values[second:])
    for split in result:
        result[split].sort()
    return result


def make_group_folds(files: list[str] | tuple[str, ...], n_splits: int = FOLD_COUNT, seed: int = SEED):
    """Return stratified group folds, using each file as a single indivisible group."""
    from sklearn.model_selection import StratifiedGroupKFold
    import numpy as np

    files = sorted(str(file).replace('\\', '/') for file in files)
    folders = np.asarray([_folder(file) for file in files])
    groups = np.asarray(files)
    splitter = StratifiedGroupKFold(n_splits=n_splits, shuffle=True, random_state=seed)
    folds = []
    for train_indexes, validation_indexes in splitter.split(np.zeros(len(files)), folders, groups):
        train_files = [files[index] for index in train_indexes]
        validation_files = [files[index] for index in validation_indexes]
        calibration_split = stratified_file_split(
            train_files,
            seed=seed + len(folds) + 1,
            ratios={'train': 0.8, 'calibration': 0.2, 'test': 0.0},
        )
        folds.append({
            'train': calibration_split['train'],
            'calibration': calibration_split['calibration'],
            'validation': validation_files,
            'folders_missing_from_validation': sorted(
                {'valve1', 'valve2', 'other'} - {_folder(file) for file in validation_files}
            ),
        })
    return folds


def _parse_timestamp(value: str, file: Path, line_number: int) -> datetime:
    try:
        return datetime.fromisoformat(value.strip())
    except (TypeError, ValueError) as exc:
        raise ValueError(f'{file.name}, ligne {line_number}: datetime invalide.') from exc


def read_skab_csv(path: str | Path, *, labeled: bool = True) -> list[dict]:
    """Read one SKAB file; preserve the source sensor-column names verbatim."""
    path = Path(path)
    with path.open('r', encoding='utf-8-sig', newline='') as source:
        reader = csv.DictReader(source, delimiter=';')
        fields = reader.fieldnames or []
        missing = [column for column in ('datetime', *SENSOR_COLUMNS) if column not in fields]
        if missing:
            raise ValueError(f'{path.name}: colonnes obligatoires absentes : {", ".join(missing)}.')
        if labeled and not {'anomaly', 'changepoint'}.issubset(fields):
            raise ValueError(f'{path.name}: colonnes anomaly et changepoint requises.')
        records = []
        for line_number, row in enumerate(reader, start=2):
            timestamp = _parse_timestamp(row.get('datetime'), path, line_number)
            try:
                values = {column: float(row[column]) if row[column].strip() else math.nan for column in SENSOR_COLUMNS}
                anomaly = int(float(row['anomaly'])) if labeled else 0
                changepoint = int(float(row['changepoint'])) if labeled else 0
            except (TypeError, ValueError) as exc:
                raise ValueError(f'{path.name}, ligne {line_number}: mesure ou label invalide.') from exc
            if anomaly not in (0, 1) or changepoint not in (0, 1):
                raise ValueError(f'{path.name}, ligne {line_number}: les labels doivent valoir 0 ou 1.')
            records.append({
                'timestamp': timestamp, 'values': values,
                'anomaly': anomaly, 'changepoint': changepoint,
            })
    if not records:
        raise ValueError(f'{path.name}: aucun relevé.')
    records.sort(key=lambda record: record['timestamp'])
    return records


def _window_feature_vector(records: list[dict]) -> tuple[float, ...]:
    import numpy as np

    vector = []
    timestamps = np.asarray([
        (row['timestamp'] - records[0]['timestamp']).total_seconds() for row in records
    ], dtype=float)
    for column in SENSOR_COLUMNS:
        values = np.asarray([row['values'][column] for row in records], dtype=float)
        valid = np.isfinite(values)
        observed = values[valid]
        observed_times = timestamps[valid]
        if len(observed) == 0:
            vector.extend((0.0,) * len(WINDOW_STATS))
            continue
        median = float(np.median(observed))
        mad = float(np.median(np.abs(observed - median)))
        if len(observed) > 1 and float(np.ptp(observed_times)) > 0:
            slope = float(np.polyfit(observed_times, observed, 1)[0])
        else:
            slope = 0.0
        vector.extend((median, mad, float(np.min(observed)), float(np.max(observed)),
                       float(observed[-1]), slope))
    return tuple(vector)


def make_time_windows(
    records: list[dict],
    file: str = 'unknown/unknown.csv',
    window_seconds: int = WINDOW_SECONDS,
    *,
    labeled: bool = True,
) -> list[Window]:
    """Create trailing `[t-window_seconds, t]` windows from actual timestamps.

    No interpolation/resampling is performed. A window label is the label on
    its right-edge observation; changepoint is retained separately for delay.
    The first `window_seconds` of each experiment are omitted.
    """
    if window_seconds <= 0:
        raise ValueError('window_seconds doit être strictement positif.')
    ordered = sorted(records, key=lambda record: record['timestamp'])
    if not ordered:
        return []
    duration = timedelta(seconds=window_seconds)
    left = 0
    result = []
    for end_index, end_record in enumerate(ordered):
        end_time = end_record['timestamp']
        start_time = end_time - duration
        if end_time - ordered[0]['timestamp'] < duration:
            continue
        while left < end_index and ordered[left]['timestamp'] < start_time:
            left += 1
        window_records = ordered[left:end_index + 1]
        result.append(Window(
            file=file.replace('\\', '/'),
            folder=_folder(file),
            anomaly_type=anomaly_type_for_file(file),
            timestamp=end_time,
            features=_window_feature_vector(window_records),
            anomaly=int(end_record['anomaly']) if labeled else 0,
            changepoint=int(end_record['changepoint']) if labeled else 0,
            all_normal=(not labeled) or all(int(row['anomaly']) == 0 for row in window_records),
            observations=len(window_records),
        ))
    return result


def _load_windows(data_dir: Path, files: list[str], *, labeled: bool = True) -> list[Window]:
    windows = []
    for relative in files:
        path = data_dir / Path(relative)
        records = read_skab_csv(path, labeled=labeled)
        windows.extend(make_time_windows(records, relative, labeled=labeled))
    return windows


def _matrix(windows: list[Window]):
    import numpy as np
    return np.asarray([window.features for window in windows], dtype=np.float64)


def _labels(windows: list[Window]):
    import numpy as np
    return np.asarray([window.anomaly for window in windows], dtype=np.int8)


def _fit_isolation_forest(train_windows: list[Window], normal_windows: list[Window], seed: int):
    from sklearn.ensemble import IsolationForest
    from sklearn.impute import SimpleImputer
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import RobustScaler

    normal = [window for window in normal_windows if window.all_normal]
    normal.extend(window for window in train_windows if window.all_normal)
    if len(normal) < 2:
        raise ValueError('Pas assez de fenêtres strictement normales pour IsolationForest.')
    model = make_pipeline(
        SimpleImputer(strategy='median'), RobustScaler(),
        IsolationForest(n_estimators=200, contamination='auto', random_state=seed, n_jobs=-1),
    )
    model.fit(_matrix(normal))
    return model


def _fit_classifier(train_windows: list[Window], seed: int):
    from sklearn.ensemble import HistGradientBoostingClassifier
    from sklearn.impute import SimpleImputer
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import RobustScaler

    if len({window.anomaly for window in train_windows}) < 2:
        raise ValueError('Les fenêtres d’entraînement du classifieur doivent contenir les deux classes.')
    model = make_pipeline(
        SimpleImputer(strategy='median'), RobustScaler(),
        HistGradientBoostingClassifier(
            learning_rate=0.08, max_iter=150, max_leaf_nodes=15,
            l2_regularization=1.0, random_state=seed,
        ),
    )
    model.fit(_matrix(train_windows), _labels(train_windows))
    return model


def _predict_scores(model_name: str, model, windows: list[Window]):
    if model_name == 'isolation_forest':
        return -model.score_samples(_matrix(windows))
    return model.predict_proba(_matrix(windows))[:, 1]


def _calibrate_threshold(scores, windows: list[Window], target_fpr: float = TARGET_FALSE_POSITIVE_RATE) -> float:
    import numpy as np

    normal_scores = np.asarray([score for score, window in zip(scores, windows) if window.anomaly == 0])
    if normal_scores.size == 0:
        raise ValueError('La calibration doit contenir des fenêtres normales.')
    return float(np.quantile(normal_scores, 1.0 - target_fpr))


def _group_windows(windows: list[Window]) -> dict[str, list[Window]]:
    grouped: dict[str, list[Window]] = defaultdict(list)
    for window in windows:
        grouped[window.file].append(window)
    return dict(grouped)


def _evaluation_labels(windows: list[Window]):
    """Pre-changepoint observations are normal for alarm scoring, by policy."""
    import numpy as np

    labels = np.asarray([window.anomaly for window in windows], dtype=np.int8)
    indexes_by_file: dict[str, list[int]] = defaultdict(list)
    for index, window in enumerate(windows):
        indexes_by_file[window.file].append(index)
    for indexes in indexes_by_file.values():
        grouped = [windows[index] for index in indexes]
        change_times = [window.timestamp for window in grouped if window.changepoint == 1]
        if change_times:
            first_change = min(change_times)
            for index in indexes:
                if windows[index].timestamp < first_change:
                    labels[index] = 0
    return labels


def _confusion_metrics(labels, predictions) -> dict:
    import numpy as np

    labels = np.asarray(labels, dtype=bool)
    predictions = np.asarray(predictions, dtype=bool)
    tp = int(np.logical_and(labels, predictions).sum())
    fp = int(np.logical_and(~labels, predictions).sum())
    fn = int(np.logical_and(labels, ~predictions).sum())
    tn = int(np.logical_and(~labels, ~predictions).sum())
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {
        'precision': precision, 'recall': recall, 'f1': f1,
        'false_positive_rate': fp / (fp + tn) if fp + tn else 0.0,
        'tp': tp, 'fp': fp, 'fn': fn, 'tn': tn,
    }


def evaluate_scores(windows: list[Window], scores, threshold: float) -> dict:
    """Evaluate alarms; early alarms before a file's first changepoint are FPs."""
    import numpy as np

    scores = np.asarray(scores, dtype=float)
    predictions = scores >= threshold
    labels = _evaluation_labels(windows)
    overall = _confusion_metrics(labels, predictions)
    by_file = {}
    groups = _group_windows(windows)
    indexes_by_file: dict[str, list[int]] = defaultdict(list)
    for index, window in enumerate(windows):
        indexes_by_file[window.file].append(index)
    for file, grouped in sorted(groups.items()):
        indexes = indexes_by_file[file]
        local_predictions = predictions[indexes]
        local_labels = labels[indexes]
        result = _confusion_metrics(local_labels, local_predictions)
        change_times = [window.timestamp for window in grouped if window.changepoint == 1]
        anomaly_times = [window.timestamp for window in grouped if window.anomaly == 1]
        first_change = min(change_times) if change_times else (min(anomaly_times) if anomaly_times else None)
        prechange = sum(
            bool(predictions[index]) and first_change is not None and windows[index].timestamp < first_change
            for index in indexes
        )
        detected_after = [
            windows[index].timestamp for index in indexes
            if predictions[index] and first_change is not None and windows[index].timestamp >= first_change
        ]
        delay = (min(detected_after) - first_change).total_seconds() if detected_after else None
        result.update({
            'folder': grouped[0].folder,
            'anomaly_type': grouped[0].anomaly_type,
            'windows': len(grouped),
            'first_event': first_change.isoformat() if first_change else None,
            'detection_delay_seconds': delay,
            'missed_detection': first_change is not None and delay is None,
            'premature_alarm_windows': int(prechange),
        })
        by_file[file] = result
    delays = [item['detection_delay_seconds'] for item in by_file.values() if item['detection_delay_seconds'] is not None]
    overall.update({
        'windows': len(windows),
        'mean_detection_delay_seconds': float(np.mean(delays)) if delays else None,
        'files_with_event': sum(item['first_event'] is not None for item in by_file.values()),
        'files_detected': sum(item['detection_delay_seconds'] is not None for item in by_file.values()),
        'files_missed': sum(bool(item['missed_detection']) for item in by_file.values()),
        'premature_alarm_windows': sum(item['premature_alarm_windows'] for item in by_file.values()),
        'by_file': by_file,
    })
    overall['by_folder'] = _aggregate_groups(by_file, 'folder')
    overall['by_anomaly_type'] = _aggregate_groups(by_file, 'anomaly_type')
    return overall


def _aggregate_groups(by_file: dict, field: str) -> dict:
    import numpy as np

    categories: dict[str, list[dict]] = defaultdict(list)
    for item in by_file.values():
        categories[item[field]].append(item)
    result = {}
    for name, items in sorted(categories.items()):
        counts = {key: sum(item[key] for item in items) for key in ('tp', 'fp', 'fn', 'tn')}
        metrics = _confusion_metrics(
            [1] * counts['tp'] + [1] * counts['fn'] + [0] * counts['fp'] + [0] * counts['tn'],
            [1] * counts['tp'] + [0] * counts['fn'] + [1] * counts['fp'] + [0] * counts['tn'],
        )
        delays = [item['detection_delay_seconds'] for item in items if item['detection_delay_seconds'] is not None]
        metrics.update({
            'files': len(items), 'windows': sum(item['windows'] for item in items),
            'files_detected': len(delays),
            'files_missed': sum(bool(item['missed_detection']) for item in items),
            'mean_detection_delay_seconds': float(np.mean(delays)) if delays else None,
            'premature_alarm_windows': sum(item['premature_alarm_windows'] for item in items),
        })
        result[name] = metrics
    return result


def _statistical_reference_fit(normal_windows: list[Window]):
    """Median/MAD reference trained exclusively on anomaly-free windows."""
    import numpy as np

    matrix = _matrix(normal_windows)
    median = np.nanmedian(matrix, axis=0)
    mad = np.nanmedian(np.abs(matrix - median), axis=0)
    scale = np.maximum(1.4826 * mad, 1e-9)
    return {'median': median, 'mad_scale': scale}


def _statistical_reference_scores(reference: dict, windows: list[Window]):
    import numpy as np

    matrix = _matrix(windows)
    return np.nanmax(np.abs(matrix - reference['median']) / reference['mad_scale'], axis=1)


def _json_metrics(metrics: dict) -> dict:
    if isinstance(metrics, dict):
        return {key: _json_metrics(value) for key, value in metrics.items()}
    if isinstance(metrics, list):
        return [_json_metrics(value) for value in metrics]
    if hasattr(metrics, 'item'):
        return metrics.item()
    return metrics


def _mean_std(rows: list[dict], keys: tuple[str, ...]) -> dict:
    import numpy as np

    result = {}
    for key in keys:
        values = [row.get(key) for row in rows if row.get(key) is not None]
        result[key] = {
            'mean': float(np.mean(values)) if values else None,
            'std': float(np.std(values, ddof=1)) if len(values) > 1 else (0.0 if values else None),
            'folds_with_value': len(values),
        }
    return result


def _windows_for(files: list[str], windows_by_file: dict[str, list[Window]]) -> list[Window]:
    return [window for file in files for window in windows_by_file.get(file, [])]


def _cross_validate(model_name: str, train_files: list[str], windows_by_file: dict[str, list[Window]], normal_windows: list[Window], seed: int) -> dict:
    import numpy as np

    folds = make_group_folds(train_files, seed=seed)
    fold_results = []
    for index, fold in enumerate(folds):
        fit_windows = _windows_for(fold['train'], windows_by_file)
        calibration_windows = _windows_for(fold['calibration'], windows_by_file)
        validation_windows = _windows_for(fold['validation'], windows_by_file)
        if not fit_windows or not calibration_windows or not validation_windows:
            raise ValueError(f'Pli {index + 1}: ensemble de fenêtres vide.')
        if model_name == 'isolation_forest':
            model = _fit_isolation_forest(fit_windows, normal_windows, seed + index)
            calibration_scores = _predict_scores(model_name, model, calibration_windows)
            validation_scores = _predict_scores(model_name, model, validation_windows)
        elif model_name == 'hist_gradient_boosting':
            model = _fit_classifier(fit_windows, seed + index)
            calibration_scores = _predict_scores(model_name, model, calibration_windows)
            validation_scores = _predict_scores(model_name, model, validation_windows)
        else:
            raise ValueError(f'Modèle CV inconnu : {model_name}.')
        threshold = _calibrate_threshold(calibration_scores, calibration_windows)
        metrics = evaluate_scores(validation_windows, validation_scores, threshold)
        fold_results.append({
            'fold': index + 1,
            'train_files': fold['train'], 'calibration_files': fold['calibration'],
            'validation_files': fold['validation'],
            'folders_missing_from_validation': fold['folders_missing_from_validation'],
            'threshold': threshold,
            'metrics': {key: metrics[key] for key in (
                'precision', 'recall', 'f1', 'false_positive_rate',
                'mean_detection_delay_seconds', 'files_detected', 'files_missed',
                'premature_alarm_windows', 'windows',
            )},
        })
    numeric = [row['metrics'] for row in fold_results]
    return {
        'folds': fold_results,
        'mean_std': _mean_std(numeric, (
            'precision', 'recall', 'f1', 'false_positive_rate',
            'mean_detection_delay_seconds',
        )),
        'folders_missing_by_fold': {
            str(row['fold']): row['folders_missing_from_validation'] for row in fold_results
        },
    }


def _fit_final_models(train_windows: list[Window], normal_windows: list[Window], seed: int) -> dict:
    return {
        'isolation_forest': _fit_isolation_forest(train_windows, normal_windows, seed),
        'hist_gradient_boosting': _fit_classifier(train_windows, seed),
    }


def _test_anomaly_proportion(records_by_file: dict[str, list[dict]]) -> dict:
    anomaly_count = 0
    row_count = 0
    by_folder: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for relative, records in records_by_file.items():
        count = sum(row['anomaly'] == 1 for row in records)
        anomaly_count += count
        row_count += len(records)
        by_folder[_folder(relative)][0] += count
        by_folder[_folder(relative)][1] += len(records)
    return {
        'anomaly_rows': anomaly_count,
        'total_rows': row_count,
        'proportion': anomaly_count / row_count if row_count else None,
        'by_folder': {
            folder: {
                'anomaly_rows': counts[0], 'total_rows': counts[1],
                'proportion': counts[0] / counts[1] if counts[1] else None,
            }
            for folder, counts in sorted(by_folder.items())
        },
    }


def _model_summary(model, metrics: dict) -> dict:
    return {
        'precision': metrics['precision'], 'recall': metrics['recall'],
        'f1': metrics['f1'], 'false_positive_rate': metrics['false_positive_rate'],
        'mean_detection_delay_seconds': metrics['mean_detection_delay_seconds'],
        'files_detected': metrics['files_detected'], 'files_missed': metrics['files_missed'],
        'premature_alarm_windows': metrics['premature_alarm_windows'],
        'by_folder': metrics['by_folder'], 'by_anomaly_type': metrics['by_anomaly_type'],
        'by_file': metrics['by_file'],
    }


def train_skab_model(data_dir: str | Path = DATA_DIR, artifact_path: str | Path = ARTIFACT_PATH, seed: int = SEED) -> dict:
    """Train, select without final-test access, evaluate once, and save outputs."""
    import joblib
    import numpy as np
    import sklearn

    data_dir, artifact_path = Path(data_dir), Path(artifact_path)
    report_path = artifact_path.with_name('skab_training_report.json')
    labeled_files = sorted(
        path.relative_to(data_dir).as_posix()
        for folder in ('valve1', 'valve2', 'other')
        for path in (data_dir / folder).glob('*.csv')
    )
    if len(labeled_files) != 34:
        raise ValueError(f'34 CSV étiquetés attendus; {len(labeled_files)} trouvés sous {data_dir}.')
    normal_relative = 'anomaly-free/anomaly-free.csv'
    if not (data_dir / normal_relative).is_file():
        raise FileNotFoundError(f'Fichier normal SKAB introuvable : {data_dir / normal_relative}')

    split = stratified_file_split(labeled_files, seed=seed)
    if any(not split[name] for name in ('train', 'calibration', 'test')):
        raise ValueError('La séparation doit contenir des fichiers train, calibration et test.')

    # Load train and calibration only. Final-test files are not opened until a
    # model has been selected from calibration and grouped CV.
    normal_records = read_skab_csv(data_dir / normal_relative, labeled=False)
    normal_windows = make_time_windows(normal_records, normal_relative, labeled=False)
    windows_by_file = {
        file: make_time_windows(read_skab_csv(data_dir / file), file)
        for file in split['train'] + split['calibration']
    }
    train_windows = _windows_for(split['train'], windows_by_file)
    calibration_windows = _windows_for(split['calibration'], windows_by_file)
    if not train_windows or not calibration_windows or not normal_windows:
        raise ValueError('Les fenêtres train, calibration et anomaly-free doivent être non vides.')

    cv = {
        model: _cross_validate(model, split['train'], windows_by_file, normal_windows, seed)
        for model in ('isolation_forest', 'hist_gradient_boosting')
    }
    models = _fit_final_models(train_windows, normal_windows, seed)
    calibration_results = {}
    thresholds = {}
    for name, model in models.items():
        scores = _predict_scores(name, model, calibration_windows)
        thresholds[name] = _calibrate_threshold(scores, calibration_windows)
        calibration_results[name] = evaluate_scores(calibration_windows, scores, thresholds[name])

    # Model selection is finalized before the test CSVs are read. Tie-breaks
    # are calibration F1, then lower mean CV false-positive rate.
    selection_order = sorted(
        models,
        key=lambda name: (
            -(cv[name]['mean_std']['f1']['mean'] or 0.0),
            -calibration_results[name]['f1'],
            cv[name]['mean_std']['false_positive_rate']['mean'] or 0.0,
        ),
    )
    selected_model = selection_order[0]
    selection_criterion = {
        'primary': 'meilleur F1 moyen de validation croisée groupée par fichier (pli validation uniquement)',
        'tie_breakers': [
            'F1 le plus élevé sur calibration finale',
            'taux de faux positifs moyen CV le plus bas',
        ],
        'final_test_used_for_selection': False,
        'selected_model': selected_model,
        'ranking': selection_order,
    }

    statistical_reference = _statistical_reference_fit(normal_windows)
    statistical_calibration_scores = _statistical_reference_scores(statistical_reference, calibration_windows)
    statistical_threshold = _calibrate_threshold(statistical_calibration_scores, calibration_windows)
    statistical_calibration = evaluate_scores(
        calibration_windows, statistical_calibration_scores, statistical_threshold,
    )
    statistical_cv = _cross_validate_statistical(
        split['train'], windows_by_file, statistical_reference, seed,
    )

    # Final test stage: each final model/reference is scored exactly once,
    # after selection has been recorded above.
    test_records_by_file = {
        file: read_skab_csv(data_dir / file, labeled=True)
        for file in split['test']
    }
    test_windows_by_file = {
        file: make_time_windows(test_records_by_file[file], file)
        for file in split['test']
    }
    test_windows = _windows_for(split['test'], test_windows_by_file)
    if not test_windows:
        raise ValueError('Aucune fenêtre calculable dans les fichiers test.')
    test_results = {}
    for name, model in models.items():
        scores = _predict_scores(name, model, test_windows)
        test_results[name] = _model_summary(model, evaluate_scores(test_windows, scores, thresholds[name]))
    statistical_test_scores = _statistical_reference_scores(statistical_reference, test_windows)
    statistical_test = _model_summary(
        None, evaluate_scores(test_windows, statistical_test_scores, statistical_threshold),
    )
    test_anomaly_proportion = _test_anomaly_proportion(test_records_by_file)

    report = {
        'version': 'SKAB v0.9 local dataset',
        'generated_at_utc': datetime.now(timezone.utc).isoformat(),
        'random_seed': seed,
        'source': 'SKAB / Skoltech Anomaly Benchmark',
        'data_dir': str(data_dir),
        'files': {
            'labeled_total': len(labeled_files),
            'normal_reference': normal_relative,
            'split': split,
            'test_file_count': len(split['test']),
        },
        'split_counts_by_folder': {
            split_name: dict(sorted(Counter(_folder(file) for file in files).items()))
            for split_name, files in split.items()
        },
        'windowing': {
            'duration_seconds': WINDOW_SECONDS,
            'interval': '[t - duration, t]',
            'feature_columns': list(SENSOR_COLUMNS),
            'window_statistics': list(WINDOW_STATS),
            'feature_names': list(FEATURE_NAMES),
            'timestamp_column': 'datetime',
            'label_at_window_end': 'anomaly',
            'changepoint_at_window_end': 'changepoint',
            'interpolation_or_resampling': False,
            'early_alarms_before_first_changepoint': 'comptées comme fausses alarmes; elles ne comptent pas comme détection événementielle',
            'missed_file_detection': 'tout fichier avec changepoint ou fenêtre anormale sans alarme à partir du premier événement compte comme manqué',
        },
        'parameters': {
            'target_calibration_false_positive_rate': TARGET_FALSE_POSITIVE_RATE,
            'group_cv': {'method': 'StratifiedGroupKFold', 'n_splits': FOLD_COUNT, 'group': 'fichier CSV', 'strata': 'dossier'},
            'isolation_forest': {'n_estimators': 200, 'contamination': 'auto', 'random_state': seed, 'fit_rows': 'fenêtres strictement normales uniquement'},
            'hist_gradient_boosting': {'learning_rate': 0.08, 'max_iter': 150, 'max_leaf_nodes': 15, 'l2_regularization': 1.0, 'random_state': seed},
            'statistical_reference': {'method': 'écart robuste médiane/MAD par variable, appris uniquement sur anomaly-free', 'threshold': 'calibré sur fenêtres normales des fichiers calibration'},
        },
        'software_versions': {'python': __import__('platform').python_version(), 'scikit_learn': sklearn.__version__, 'numpy': np.__version__},
        'model_selection': selection_criterion,
        'calibration': {
            'isolation_forest': _model_summary(models['isolation_forest'], calibration_results['isolation_forest']),
            'hist_gradient_boosting': _model_summary(models['hist_gradient_boosting'], calibration_results['hist_gradient_boosting']),
            'statistical_reference': _model_summary(None, statistical_calibration),
            'thresholds': thresholds | {'statistical_reference': statistical_threshold},
        },
        'cross_validation': {
            **cv,
            'statistical_reference': statistical_cv,
        },
        'test': {
            'file_count': len(split['test']),
            'files': split['test'],
            'raw_row_anomaly_proportion': test_anomaly_proportion,
            'window_anomaly_proportion': float(np.mean(_labels(test_windows))),
            'metrics': {
                'isolation_forest': test_results['isolation_forest'],
                'hist_gradient_boosting': test_results['hist_gradient_boosting'],
                'statistical_reference_not_live_app_score': statistical_test,
            },
            'evaluated_after_model_selection_only': True,
        },
        'application_score_reference': {
            'status': 'not_evaluated',
            'reason': 'Le score live _score requiert seuil_min/seuil_max configurés par capteur; SKAB ne fournit pas de limites opérationnelles correspondant aux huit signaux. Aucun score live de l’application n’est inventé.',
        },
        'limitations': [
            'SKAB est un banc d’essai de pompe/circuit de circulation, pas les capteurs des machines SmartFactory.',
            'Le test final ne comprend que 7 fichiers; les résultats par dossier, notamment valve2, ont une forte incertitude.',
            'Les anomalies constituent environ 35 % du test selon les labels; cette prévalence ne représente pas nécessairement une usine en exploitation.',
            'La référence statistique médiane/MAD est un benchmark explicite, pas le score live de l’application.',
            'Les fenêtres clairsemées dues aux pas irréguliers ne sont ni rééchantillonnées ni interpolées.',
        ],
    }
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump({
        'models': models,
        'selected_model': selected_model,
        'thresholds': thresholds,
        'statistical_reference': statistical_reference,
        'feature_names': FEATURE_NAMES,
        'metadata': report,
    }, artifact_path, compress=3)
    report_path.write_text(json.dumps(_json_metrics(report), indent=2, ensure_ascii=False), encoding='utf-8')
    return report


def _cross_validate_statistical(train_files: list[str], windows_by_file: dict[str, list[Window]], reference: dict, seed: int) -> dict:
    import numpy as np

    folds = make_group_folds(train_files, seed=seed)
    results = []
    for index, fold in enumerate(folds):
        calibration = _windows_for(fold['calibration'], windows_by_file)
        validation = _windows_for(fold['validation'], windows_by_file)
        scores_cal = _statistical_reference_scores(reference, calibration)
        threshold = _calibrate_threshold(scores_cal, calibration)
        metrics = evaluate_scores(validation, _statistical_reference_scores(reference, validation), threshold)
        results.append({
            'fold': index + 1,
            'train_files': fold['train'], 'calibration_files': fold['calibration'],
            'validation_files': fold['validation'],
            'folders_missing_from_validation': fold['folders_missing_from_validation'],
            'threshold': threshold,
            'metrics': {key: metrics[key] for key in (
                'precision', 'recall', 'f1', 'false_positive_rate',
                'mean_detection_delay_seconds', 'files_detected', 'files_missed',
                'premature_alarm_windows', 'windows',
            )},
        })
    return {
        'folds': results,
        'mean_std': _mean_std([row['metrics'] for row in results], (
            'precision', 'recall', 'f1', 'false_positive_rate', 'mean_detection_delay_seconds',
        )),
        'folders_missing_by_fold': {
            str(row['fold']): row['folders_missing_from_validation'] for row in results
        },
    }


def skab_artifact_status() -> dict:
    """Return cached model/report readiness without altering the artifacts."""
    if not ARTIFACT_PATH.is_file():
        return {
            'ready': False,
            'model_name': 'SKAB benchmark (IsolationForest / HistGradientBoostingClassifier)',
            'metadata': None,
            'detail': 'Entraînez le benchmark avec ml/train_skab.py.',
        }
    try:
        import joblib
        artifact = joblib.load(ARTIFACT_PATH)
        metadata = artifact['metadata']
        return {
            'ready': True,
            'model_name': metadata.get('model_selection', {}).get('selected_model'),
            'selected_model': artifact.get('selected_model'),
            'metadata': metadata,
            'artifact_path': str(ARTIFACT_PATH),
            'report_path': str(REPORT_PATH),
            'detail': None,
        }
    except (ImportError, OSError, KeyError, ValueError, TypeError) as error:
        return {
            'ready': False,
            'model_name': 'SKAB benchmark',
            'metadata': None,
            'detail': f'Artefact SKAB illisible : {error}',
        }
