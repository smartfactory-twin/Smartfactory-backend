from django.contrib import admin

from .models import Alerte, Notification, PreferenceNotification


@admin.register(Alerte)
class AlerteAdmin(admin.ModelAdmin):
    list_display = ('reference', 'machine', 'capteur', 'niveau', 'statut',
                    'valeur', 'seuil', 'unite', 'nb_occurrences', 'date_declenchement')
    list_filter = ('niveau', 'statut', 'type_alerte', 'machine')
    search_fields = ('reference', 'message', 'capteur__identifiant')
    readonly_fields = ('reference', 'created_at', 'updated_at')
    date_hierarchy = 'date_declenchement'


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ('titre', 'utilisateur', 'type', 'niveau', 'lue', 'date_creation')
    list_filter = ('lue', 'niveau', 'type')
    search_fields = ('titre', 'message')


@admin.register(PreferenceNotification)
class PreferenceNotificationAdmin(admin.ModelAdmin):
    list_display = ('utilisateur', 'in_app', 'email', 'sms', 'niveau_min_email')
    list_filter = ('in_app', 'email', 'sms')
