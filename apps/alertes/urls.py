from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import (
    AlertesParMachineView,
    AlerteCompteurView,
    AlerteViewSet,
    MonCanauxNotificationView,
    NotificationViewSet,
)

router = DefaultRouter()
router.register(r'alertes', AlerteViewSet, basename='alerte')
router.register(r'notifications', NotificationViewSet, basename='notification')

urlpatterns = [
    path('alertes/aggregation/par-machine/', AlertesParMachineView.as_view(),
         name='alertes-par-machine'),
    # Voie explicite (pas de ViewSet) : un seul objet, celui de l'utilisateur.
    path('canaux-notification/mien/', MonCanauxNotificationView.as_view(),
         name='canaux-notification-mien'),
    # Alias du compteur d'alertes actives hors du routeur.
    path('alertes/compteur/', AlerteCompteurView.as_view(), name='alerte-compteur'),
    *router.urls,
]
