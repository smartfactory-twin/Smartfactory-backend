import logging

from django.db.models.signals import post_save
from django.dispatch import receiver

from apps.equipements.models import Reading

from .engine import evaluer_lecture

logger = logging.getLogger(__name__)


@receiver(post_save, sender=Reading, dispatch_uid='alertes_post_save_reading')
def alertes_sur_nouvelle_lecture(sender, instance, created, raw=False, **kwargs):

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
