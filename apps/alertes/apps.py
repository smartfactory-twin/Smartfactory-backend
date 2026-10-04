from django.apps import AppConfig


class AlertesConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.alertes'
    label = 'alertes'
    verbose_name = "Alertes & Notifications"

    def ready(self):
        # Branche le signal `post_save` sur `Reading` : c'est le SEUL point
        # d'accroche du Module 8. Il couvre nativement toutes les voies
        # d'ingestion existantes (POST /readings/, import CSV, import JSON)
        # sans dupliquer ni modifier la logique d'ingestion du Module 3.
        from . import signals  # noqa: F401
