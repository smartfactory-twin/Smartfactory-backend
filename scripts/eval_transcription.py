#!/usr/bin/env python
"""Evaluate /api/voice/transcribe/ using a filename,reference CSV."""
import argparse
import csv
import json
import os
import re
import statistics
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path


IDENTIFIER = re.compile(r'(?<![A-Z0-9])(?:OT|[A-Z][A-Z0-9]*(?:-[A-Z0-9]+)+)(?![A-Z0-9])', re.IGNORECASE)
WORD = re.compile(r"[\wÀ-ÿ]+", re.UNICODE)


def normalize(text):
    return WORD.findall((text or '').casefold())


def edit_distance(left, right):
    previous = list(range(len(right) + 1))
    for row, token in enumerate(left, 1):
        current = [row]
        for column, other in enumerate(right, 1):
            current.append(min(
                current[-1] + 1,
                previous[column] + 1,
                previous[column - 1] + (token != other),
            ))
        previous = current
    return previous[-1]


def post_audio(endpoint, token, path):
    boundary = f'----TranscriptionEval{uuid.uuid4().hex}'
    content_type = {
        '.wav': 'audio/wav', '.webm': 'audio/webm', '.ogg': 'audio/ogg',
        '.mp3': 'audio/mpeg', '.mpeg': 'audio/mpeg', '.mp4': 'audio/mp4',
        '.m4a': 'audio/mp4',
    }.get(path.suffix.lower(), 'application/octet-stream')
    body = (
        f'--{boundary}\r\nContent-Disposition: form-data; name="audio"; filename="{path.name}"\r\n'
        f'Content-Type: {content_type}\r\n\r\n'
    ).encode() + path.read_bytes() + f'\r\n--{boundary}--\r\n'.encode()
    request = urllib.request.Request(
        endpoint, data=body, method='POST',
        headers={
            'Authorization': f'Bearer {token}',
            'Content-Type': f'multipart/form-data; boundary={boundary}',
            'User-Agent': 'SmartFactoryTwin-TranscriptionEval/1.0',
        },
    )
    started = time.perf_counter()
    with urllib.request.urlopen(request, timeout=180) as response:
        payload = json.loads(response.read().decode('utf-8'))
    return payload, (time.perf_counter() - started) * 1000


def percentile95(values):
    ordered = sorted(values)
    return ordered[max(0, (95 * len(ordered) + 99) // 100 - 1)]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('audio_dir', type=Path)
    parser.add_argument('references_csv', type=Path, help='CSV UTF-8 avec les colonnes filename,reference')
    parser.add_argument('--endpoint', default='http://127.0.0.1:8000/api/voice/transcribe/')
    args = parser.parse_args()
    token = os.environ.get('VOICE_ACCESS_TOKEN', '')
    if not token:
        parser.error('Définissez VOICE_ACCESS_TOKEN dans l’environnement (ne le passez pas en argument).')

    rows = []
    with args.references_csv.open(encoding='utf-8-sig', newline='') as source:
        for row in csv.DictReader(source):
            if row.get('filename') and row.get('reference') is not None:
                rows.append(row)
    if not rows:
        parser.error('Le CSV doit contenir au moins une ligne filename,reference.')

    ref_words = predicted_words = edit_total = 0
    latencies = []
    expected_ids = recognized_ids = 0
    errors = 0
    for row in rows:
        audio_path = args.audio_dir / row['filename']
        try:
            payload, latency = post_audio(args.endpoint, token, audio_path)
            hypothesis = payload.get('text', '')
            reference_tokens = normalize(row['reference'])
            hypothesis_tokens = normalize(hypothesis)
            edit_total += edit_distance(reference_tokens, hypothesis_tokens)
            ref_words += len(reference_tokens)
            predicted_words += len(hypothesis_tokens)
            latencies.append(latency)
            ids = [value.upper() for value in IDENTIFIER.findall(row['reference'])]
            expected_ids += len(ids)
            recognized = [value.upper() for value in IDENTIFIER.findall(hypothesis)]
            recognized_ids += sum(identifier in recognized for identifier in ids)
        except (OSError, urllib.error.HTTPError, urllib.error.URLError, ValueError) as exc:
            errors += 1
            print(f'ERREUR {row["filename"]}: {type(exc).__name__}')

    print(f'Fichiers évalués: {len(rows)} ; erreurs HTTP/lecture: {errors}')
    print(f'WER: {edit_total / max(ref_words, 1):.4f} ({edit_total} éditions / {ref_words} mots de référence)')
    print(f'Médiane latence: {statistics.median(latencies):.1f} ms' if latencies else 'Médiane latence: indisponible')
    print(f'P95 latence: {percentile95(latencies):.1f} ms' if latencies else 'P95 latence: indisponible')
    print(f'Identifiants reconnus: {recognized_ids}/{expected_ids} ({recognized_ids / max(expected_ids, 1):.1%})')
    print(f'Mots produits (diagnostic): {predicted_words}')


if __name__ == '__main__':
    main()
