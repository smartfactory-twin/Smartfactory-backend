"""Train/evaluate a four-class YOLO model for Sprint 4 visual inspections.

Requires an annotated Ultralytics dataset YAML. This project does not ship a
dataset or pretrained industrial weights; do not use the demo mock results as
an evaluation substitute.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description='Entraîne et évalue le modèle de défauts YOLO.')
    parser.add_argument('--data', required=True, help='Chemin vers le data.yaml Ultralytics annoté.')
    parser.add_argument('--base', default='yolov8n.pt', help='Poids de base Ultralytics (téléchargés au premier lancement).')
    parser.add_argument('--epochs', type=int, default=100)
    parser.add_argument('--imgsz', type=int, default=640)
    parser.add_argument('--device', default='cpu', help='cpu, 0 (premier GPU), etc.')
    parser.add_argument('--project', default='ml/runs/vision')
    parser.add_argument('--name', default='smartfactory-defects')
    args = parser.parse_args()
    dataset = Path(args.data).resolve()
    if not dataset.is_file():
        parser.error(f'Dataset introuvable: {dataset}')
    try:
        from ultralytics import YOLO
    except ImportError as exc:
        raise SystemExit('Installe les dépendances avec: pip install -r requirements-vision.txt') from exc

    model = YOLO(args.base)
    training = model.train(data=str(dataset), epochs=args.epochs, imgsz=args.imgsz,
                           device=args.device, project=args.project, name=args.name)
    best = Path(training.save_dir) / 'weights' / 'best.pt'
    if not best.is_file():
        raise SystemExit(f'Poids best.pt introuvables après entraînement: {best}')
    evaluator = YOLO(str(best))
    metrics = evaluator.val(data=str(dataset), imgsz=args.imgsz, device=args.device, split='test')
    names = metrics.names
    labels = list(names.values()) if isinstance(names, dict) else list(names)
    normalized = {str(label).strip().lower() for label in labels}
    alias_groups = {
        'Fissure': {'fissure', 'crack', 'fracture'},
        'Corrosion': {'corrosion', 'rust', 'rouille'},
        'Usure': {'usure', 'wear', 'abrasion'},
        'Fuite': {'fuite', 'leak'},
    }
    mapped = {canonical for canonical, aliases in alias_groups.items() if normalized & aliases}
    map50 = float(metrics.box.map50)
    report = {
        'model': 'YOLOv8', 'weights': str(best.resolve()), 'dataset_yaml': str(dataset),
        'class_names': labels,
        'required_defect_classes_present': len(mapped) == 4,
        'missing_defect_classes': sorted(set(alias_groups) - mapped),
        'metrics': {'map50': round(map50, 4), 'map50_95': round(float(metrics.box.map), 4)},
        'target_map50': 0.80, 'target_met': map50 >= 0.80,
        'evaluation_split': 'test',
        'note': 'Le résultat dépend du dataset annoté fourni et du partage train/val/test défini dans son YAML.',
    }
    report_path = Path(training.save_dir) / 'evaluation.json'
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding='utf-8')
    print(json.dumps(report, indent=2, ensure_ascii=False))
    print(f'Configure VISION_AI_BACKEND=yolo et VISION_AI_MODEL_PATH={best.resolve()}')


if __name__ == '__main__':
    main()
