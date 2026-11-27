from django.apps import AppConfig


class AlertesConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.alertes'
    label = 'alertes'
    verbose_name = "Alertes & Notifications"

    def ready(self):
      
        from . import signals  
