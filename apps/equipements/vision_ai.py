"""Module 4 — Inspection visuelle : couche de service d'analyse IA.

Le service expose un backend de démonstration et un backend Ultralytics/YOLO
configurable. Le backend YOLO attend un modèle de détection entraîné avec des
classes de défauts reconnues; aucun poids n'est livré avec le dépôt.

Contrat de `analyze_image(image)` :
    {
        "defect_detected": bool,
        "defect_type": str | None,
        "confidence": float,        # 0.0 – 1.0
        "localization": str | None,
        "comment": str,
    }
"""
import hashlib
import os
import unicodedata
from functools import lru_cache

from django.conf import settings


class VisionAIService:
    """Interface d'un service d'analyse d'image."""

    name = 'base'

    def analyze_image(self, image):
        """Analyse une image et retourne le dictionnaire de résultat."""
        raise NotImplementedError(
            "VisionAIService.analyze_image() doit être implémentée."
        )


DEFECT_TYPES = ['Fissure', 'Corrosion', 'Usure', 'Fuite']
LOCALIZATIONS = ['haut-gauche', 'haut-droite', 'centre', 'bas-gauche', 'bas-droite']


def _normalize_label(label):
    normalized = unicodedata.normalize('NFKD', str(label)).encode('ascii', 'ignore').decode()
    return ''.join(char for char in normalized.lower() if char.isalnum())


YOLO_DEFECT_LABELS = {
    'fissure': ('fissure', 'crack', 'fracture'),
    'corrosion': ('corrosion', 'rust', 'rouille'),
    'usure': ('usure', 'wear', 'abrasion'),
    'fuite': ('fuite', 'leak'),
}


class UltralyticsVisionAIService(VisionAIService):
    """Analyse une image avec des poids de détection Ultralytics locaux."""

    name = 'yolo'

    @staticmethod
    @lru_cache(maxsize=2)
    def _load_model(model_path):
        if not model_path or not os.path.isfile(model_path):
            raise RuntimeError(
                'Modèle YOLO introuvable. Configure VISION_AI_MODEL_PATH avec le chemin '
                'des poids entraînés (fichier .pt).'
            )
        try:
            from ultralytics import YOLO
        except ImportError as exc:
            raise RuntimeError(
                'Le backend YOLO est activé mais ultralytics n’est pas installé. '
                'Installe les dépendances vision indiquées dans le guide Sprint 4.'
            ) from exc
        return YOLO(model_path)

    @staticmethod
    def _class_map(names):
        items = names.items() if isinstance(names, dict) else enumerate(names)
        class_map = {}
        for class_id, label in items:
            normalized = _normalize_label(label)
            for defect, aliases in YOLO_DEFECT_LABELS.items():
                if normalized in {_normalize_label(alias) for alias in aliases}:
                    class_map[int(class_id)] = defect.title()
                    break
        if not class_map:
            raise RuntimeError(
                'Les classes du modèle YOLO ne correspondent pas aux défauts attendus '
                '(Fissure/Crack, Corrosion/Rust, Usure/Wear, Fuite/Leak).'
            )
        return class_map

    @staticmethod
    def _location(box, width, height):
        x1, y1, x2, y2 = box
        x = (x1 + x2) / 2 / max(width, 1)
        y = (y1 + y2) / 2 / max(height, 1)
        horizontal = 'gauche' if x < 1 / 3 else 'droite' if x > 2 / 3 else ''
        vertical = 'haut' if y < 1 / 3 else 'bas' if y > 2 / 3 else ''
        if horizontal and vertical:
            return f'{vertical}-{horizontal}'
        if horizontal:
            return f'centre-{horizontal}'
        if vertical:
            return f'{vertical}-centre'
        return 'centre'

    def analyze_image(self, image):
        from PIL import Image

        model_path = str(getattr(settings, 'VISION_AI_MODEL_PATH', '') or '')
        model = self._load_model(model_path)
        image.seek(0)
        with Image.open(image) as opened:
            source = opened.convert('RGB')
        image.seek(0)
        result = model.predict(
            source=source,
            conf=float(getattr(settings, 'VISION_AI_CONFIDENCE_THRESHOLD', 0.25)),
            verbose=False,
        )[0]
        class_map = self._class_map(result.names)
        candidates = []
        boxes = result.boxes
        if boxes is not None:
            for box in boxes:
                class_id = int(box.cls[0].item())
                defect = class_map.get(class_id)
                if defect:
                    coords = box.xyxy[0].tolist()
                    candidates.append((float(box.conf[0].item()), defect, coords))

        if not candidates:
            return {
                'defect_detected': False,
                'defect_type': 'Normal',
                'confidence': 0.0,
                'localization': None,
                'comment': 'Aucun défaut reconnu au-dessus du seuil de confiance configuré.',
                'model': 'ultralytics-yolo',
                'detections': [],
            }

        candidates.sort(key=lambda item: item[0], reverse=True)
        confidence, defect, coords = candidates[0]
        localization = self._location(coords, *source.size)
        detections = [
            {
                'defect_type': kind,
                'confidence': round(score, 4),
                'box': [round(value, 2) for value in box],
            }
            for score, kind, box in candidates
        ]
        return {
            'defect_detected': True,
            'defect_type': defect,
            'confidence': round(confidence, 4),
            'localization': localization,
            'comment': f'Défaut « {defect} » détecté dans la zone {localization}.',
            'model': 'ultralytics-yolo',
            'detections': detections,
        }


class MockVisionAIService(VisionAIService):
    """Service de démonstration déterministe (aucun vrai modèle IA).

    Le résultat est dérivé de l'empreinte SHA-256 des octets de l'image : une
    même image produit toujours le même résultat, ce qui permet de tester tout
    le workflow sans dépendre d'un modèle externe.
    """

    name = 'mock'

    @staticmethod
    def _read_bytes(image):
        try:
            image.seek(0)
        except (AttributeError, ValueError):
            pass
        data = image.read() if hasattr(image, 'read') else bytes(image)
        try:
            image.seek(0)
        except (AttributeError, ValueError):
            pass
        return data

    def analyze_image(self, image):
        data = self._read_bytes(image)
        digest = hashlib.sha256(data).hexdigest()
        seed = int(digest[:8], 16)

        detected = (seed % 100) < 60  # ~60 % de défauts détectés en démo
        if detected:
            defect_type = DEFECT_TYPES[seed % len(DEFECT_TYPES)]
            localization = LOCALIZATIONS[(seed // 7) % len(LOCALIZATIONS)]
            confidence = round(0.70 + (seed % 30) / 100, 2)
            comment = (
                f"Défaut de type « {defect_type} » détecté "
                f"sur la zone {localization}."
            )
        else:
            defect_type = 'Normal'
            localization = None
            confidence = round(0.80 + (seed % 20) / 100, 2)
            comment = "Aucun défaut visuel détecté. État conforme."

        return {
            'defect_detected': detected,
            'defect_type': defect_type,
            'confidence': confidence,
            'localization': localization,
            'comment': comment,
        }


# Registre des implémentations disponibles.
VISION_SERVICES = {
    'mock': MockVisionAIService,
    'yolo': UltralyticsVisionAIService,
}


def get_vision_service():
    """Retourne l'implémentation de `VisionAIService` configurée.

    Sélection via `settings.VISION_AI_BACKEND` (`mock` ou `yolo`).
    """
    backend = getattr(settings, 'VISION_AI_BACKEND', 'mock')
    service_cls = VISION_SERVICES.get(backend)
    if service_cls is None:
        raise ValueError(f"Backend Vision AI inconnu : {backend!r}. Valeurs : mock, yolo.")
    return service_cls()
