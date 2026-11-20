from datetime import datetime, timedelta

import pytest

from apps.equipements.skab_ml import (
    Window,
    make_group_folds,
    make_time_windows,
    stratified_file_split,
    evaluate_scores,
)


def _files():
    return (
        [f'valve1/{index}.csv' for index in range(16)]
        + [f'valve2/{index}.csv' for index in range(4)]
        + [f'other/{index}.csv' for index in range(1, 15)]
    )


def _record(timestamp, value, anomaly=0, changepoint=0):
    return {
        'timestamp': timestamp,
        'values': {
            'Accelerometer1RMS': value,
            'Accelerometer2RMS': value + 1,
            'Current': value + 2,
            'Pressure': value + 3,
            'Temperature': value + 4,
            'Thermocouple': value + 5,
            'Voltage': value + 6,
            'Volume Flow RateRMS': value + 7,
        },
        'anomaly': anomaly,
        'changepoint': changepoint,
    }


def test_file_split_is_deterministic_disjoint_and_stratified_by_folder():
    files = _files()
    first = stratified_file_split(files, seed=42)
    second = stratified_file_split(files, seed=42)

    assert first == second
    assert len(first['train']) == 20
    assert len(first['calibration']) == 7
    assert len(first['test']) == 7
    assert set(first['train']).isdisjoint(first['calibration'])
    assert set(first['train']).isdisjoint(first['test'])
    assert set(first['calibration']).isdisjoint(first['test'])
    assert set().union(*map(set, first.values())) == set(files)
    assert {name: sum(path.startswith(f'{name}/') for path in first['train']) for name in ('valve1', 'valve2', 'other')} == {
        'valve1': 10, 'valve2': 2, 'other': 8,
    }
    assert {name: sum(path.startswith(f'{name}/') for path in first['calibration']) for name in ('valve1', 'valve2', 'other')} == {
        'valve1': 3, 'valve2': 1, 'other': 3,
    }


def test_group_cv_keeps_files_intact_and_reports_missing_folders():
    train_files = stratified_file_split(_files(), seed=42)['train']
    folds = make_group_folds(train_files, n_splits=5, seed=42)

    validation_files = []
    for fold in folds:
        train = set(fold['train'])
        calibration = set(fold['calibration'])
        validation = set(fold['validation'])
        assert train.isdisjoint(calibration)
        assert train.isdisjoint(validation)
        assert calibration.isdisjoint(validation)
        assert 'folders_missing_from_validation' in fold
        validation_files.extend(validation)
    assert sorted(validation_files) == sorted(train_files)


def test_windows_use_elapsed_time_and_right_edge_labels_with_irregular_samples():
    start = datetime(2026, 1, 1)
    seconds = (0, 5, 16, 30, 31, 65)
    records = [
        _record(start + timedelta(seconds=second), float(second),
                anomaly=1 if second == 31 else 0,
                changepoint=1 if second == 31 else 0)
        for second in seconds
    ]

    windows = make_time_windows(records, 'other/1.csv', window_seconds=30)

    at_30s = next(window for window in windows if window.timestamp == start + timedelta(seconds=30))
    at_31s = next(window for window in windows if window.timestamp == start + timedelta(seconds=31))
    assert at_30s.observations == 4  # timestamps 0, 5, 16, 30
    assert at_31s.observations == 4  # timestamps 5, 16, 30, 31; not a 30-row window
    assert at_30s.anomaly == 0
    assert at_31s.anomaly == 1
    assert at_31s.changepoint == 1
    assert len(at_31s.features) == 8 * 6


def test_premature_alarm_is_counted_as_false_and_not_as_detection_delay():
    start = datetime(2026, 1, 1)
    windows = [
        Window('valve1/1.csv', 'valve1', 'fermeture valve entrée', start,
               (0.0,), 0, 0, True, 1),
        Window('valve1/1.csv', 'valve1', 'fermeture valve entrée', start + timedelta(seconds=5),
               (0.0,), 1, 1, False, 1),
        Window('valve1/1.csv', 'valve1', 'fermeture valve entrée', start + timedelta(seconds=6),
               (0.0,), 1, 0, False, 1),
    ]

    metrics = evaluate_scores(windows, [0.9, 0.1, 0.1], threshold=0.5)

    assert metrics['fp'] == 1
    assert metrics['premature_alarm_windows'] == 1
    assert metrics['files_missed'] == 1
    assert metrics['mean_detection_delay_seconds'] is None


def test_anomalous_file_without_changepoint_is_counted_as_missed_without_alarm():
    timestamp = datetime(2026, 1, 1)
    windows = [
        Window('other/2.csv', 'other', 'fuite', timestamp,
               (0.0,), 0, 0, True, 1),
        Window('other/2.csv', 'other', 'fuite', timestamp + timedelta(seconds=1),
               (0.0,), 1, 0, False, 1),
    ]

    metrics = evaluate_scores(windows, [0.1, 0.1], threshold=0.5)

    assert metrics['files_with_event'] == 1
    assert metrics['files_missed'] == 1
    assert metrics['by_file']['other/2.csv']['first_event'] == (timestamp + timedelta(seconds=1)).isoformat()


@pytest.mark.parametrize('bad_window_seconds', [0, -1])
def test_time_window_duration_must_be_positive(bad_window_seconds):
    with pytest.raises(ValueError, match='strictement positif'):
        make_time_windows([], window_seconds=bad_window_seconds)
