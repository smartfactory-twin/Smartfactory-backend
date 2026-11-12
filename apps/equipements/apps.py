from django.apps import AppConfig
class EquipementsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.equipements'
    verbose_name = 'Gestion des équipements'

    def ready(self):
        from django.db.models.signals import post_save
        from .models import Reading
        from .realtime import on_reading_created

        post_save.connect(
            on_reading_created,
            sender=Reading,
            dispatch_uid='equipements_publish_reading_ws',
        )
