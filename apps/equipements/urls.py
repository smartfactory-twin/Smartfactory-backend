from rest_framework.routers import DefaultRouter
from .views import (
    UsineViewSet, ZoneViewSet, LigneProductionViewSet,
    MachineViewSet, ComposantViewSet, DocumentViewSet,
)

router = DefaultRouter()
router.register(r'usines', UsineViewSet, basename='usine')
router.register(r'zones', ZoneViewSet, basename='zone')
router.register(r'lignes', LigneProductionViewSet, basename='ligne')
router.register(r'machines', MachineViewSet, basename='machine')
router.register(r'composants', ComposantViewSet, basename='composant')
router.register(r'documents', DocumentViewSet, basename='document')

urlpatterns = router.urls
