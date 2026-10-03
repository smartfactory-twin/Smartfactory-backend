"""Module 4 — Inspection visuelle : couche de service d'analyse IA.

Ce module définit l'interface `VisionAIService` ainsi qu'une implémentation de
démonstration (`MockVisionAIService`). Aucun modèle de Computer Vision réel
n'est embarqué : la sélection de l'implémentation se fait via le réglage
`VISION_AI_BACKEND`, ce qui permet de brancher un vrai modèle plus tard sans
modifier les vues ni le reste de l'application.

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

from django.conf import settings


class VisionAIService:
    """Interface d'un service d'analyse d'image."""

    name = 'base'

    def analyze_image(self, image):
        """Analyse une image et retourne le dictionnaire de résultat."""
        raise NotImplementedError(
            "VisionAIService.analyze_image() doit être implémentée."
        )


DEFECT_TYPES = ['Fissure', 'Corrosion', 'Usure', 'Déformation', 'Fuite']
LOCALIZATIONS = ['haut-gauche', 'haut-droite', 'centre', 'bas-gauche', 'bas-droite']


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
            defect_type = None
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
}


def get_vision_service():
    """Retourne l'implémentation de `VisionAIService` configurée.

    Remplaçable via `settings.VISION_AI_BACKEND` (défaut : 'mock').
    """
    backend = getattr(settings, 'VISION_AI_BACKEND', 'mock')
    service_cls = VISION_SERVICES.get(backend, MockVisionAIService)
    return service_cls()
