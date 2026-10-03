from django.urls import path
from rest_framework.routers import DefaultRouter
from .views import (
    UsineViewSet, ZoneViewSet, LigneProductionViewSet,
    MachineViewSet, ComposantViewSet, DocumentViewSet,
    SensorViewSet, ReadingViewSet, InspectionVisuelleViewSet,
)

router = DefaultRouter()
router.register(r'usines', UsineViewSet, basename='usine')
router.register(r'zones', ZoneViewSet, basename='zone')
router.register(r'lignes', LigneProductionViewSet, basename='ligne')
router.register(r'machines', MachineViewSet, basename='machine')
router.register(r'composants', ComposantViewSet, basename='composant')
router.register(r'documents', DocumentViewSet, basename='document')
router.register(r'capteurs', SensorViewSet, basename='capteur')
router.register(r'readings', ReadingViewSet, basename='reading')
router.register(r'inspections', InspectionVisuelleViewSet, basename='inspection')

urlpatterns = [
    path('hierarchie/export_csv/', UsineViewSet.as_view({'get': 'export_csv'}), name='hierarchie-export-csv'),
    path('hierarchie/preview_csv/', UsineViewSet.as_view({'post': 'preview_csv'}), name='hierarchie-preview-csv'),
    path('hierarchie/import_csv/', UsineViewSet.as_view({'post': 'import_csv'}), name='hierarchie-import-csv'),
    *router.urls
]

