"""Module 8 — Point d'accroche de la génération automatique (UC-26).

Un `post_save` sur `Reading` suffit à couvrir **toutes** les voies
d'ingestion déjà en place dans le Module 3 :

* `POST /api/readings/`  → `ReadingViewSet.create()`  → `serializer.save()`
* `import_csv` / `import_json` → `Reading.objects.get_or_create(...)`
* `preprocess` → `Reading.objects.create(...)` (mesures interpolées)

Aucune ligne du Module 3 n'est modifiée, et aucune logique parallèle
« jamais appelée » n'est introduite : le signal s'insère dans le flux
existant.

Deux garde-fous :

* `raw=True` (fixtures) → ignoré ;
* `created=False` → ignoré. `apply_preprocessing()` fait un
  `save(update_fields=...)` qui repasserait sur le signal ; on ne veut pas
  rejouer le moteur à chaque prétraitement.
"""
import logging

from django.db.models.signals import post_save
from django.dispatch import receiver

from apps.equipements.models import Reading

from .engine import evaluer_lecture

logger = logging.getLogger(__name__)


@receiver(post_save, sender=Reading, dispatch_uid='alertes_post_save_reading')
def alertes_sur_nouvelle_lecture(sender, instance, created, raw=False, **kwargs):
    """Évalue chaque nouvelle mesure et déclenche / met à jour les alertes."""
    if raw or not created:
        return
    try:
        evaluer_lecture(instance)
    except Exception:
        # Une alerte ne doit jamais faire échouer l'ingestion d'une mesure.
        logger.exception(
            'Module 8 — échec de l\'évaluation de la mesure #%s (capteur %s).',
            instance.pk, instance.sensor_id,
        )
