from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

from apps.equipements.views import (
    ReadingViewSet, SensorViewSet, InspectionVisuelleViewSet,
)

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/auth/', include('apps.accounts.urls')),
    path('api/equipements/', include('apps.equipements.urls')),

    # ── Module 3 — UC-08 : import CSV de création de capteurs (alias) ──────────
    # CSV → création de Sensor (jamais de mesures). Distinct de UC-09 ci-dessous.
    path('api/capteurs/preview_csv/', SensorViewSet.as_view({'post': 'preview_csv'}),
         name='capteurs-preview-csv'),
    path('api/capteurs/import_csv/', SensorViewSet.as_view({'post': 'import_csv'}),
         name='capteurs-import-csv'),

    # ── Module 3 — UC-09 : ingestion IoT (endpoint du cahier des charges) ──────
    # POST /api/readings/  → reçoit les mesures d'une passerelle IoT.
    path('api/readings/', ReadingViewSet.as_view({'get': 'list', 'post': 'create'}),
         name='readings-list'),
    path('api/readings/preview_csv/', ReadingViewSet.as_view({'post': 'preview_csv'}),
         name='readings-preview-csv'),
    path('api/readings/import_csv/', ReadingViewSet.as_view({'post': 'import_csv'}),
         name='readings-import-csv'),
    path('api/readings/preview_json/', ReadingViewSet.as_view({'post': 'preview_json'}),
         name='readings-preview-json'),
    path('api/readings/import_json/', ReadingViewSet.as_view({'post': 'import_json'}),
         name='readings-import-json'),
    path('api/readings/preprocess/', ReadingViewSet.as_view({'post': 'preprocess'}),
         name='readings-preprocess'),
    path('api/readings/<int:pk>/', ReadingViewSet.as_view({
        'get': 'retrieve', 'put': 'update', 'patch': 'partial_update', 'delete': 'destroy',
    }), name='readings-detail'),

    # ── Module 4 — UC-10 : inspection visuelle par IA (alias canonique) ────────
    # POST /api/inspections/            crée une inspection (machine + image)
    # GET  /api/inspections/            historique paginé/filtrable
    # GET  /api/inspections/{id}/       détail
    # POST /api/inspections/{id}/analyze/  lance l'analyse IA
    # DELETE /api/inspections/{id}/     suppression (ADMIN)
    path('api/inspections/',
         InspectionVisuelleViewSet.as_view({'get': 'list', 'post': 'create'}),
         name='inspections-list'),
    path('api/inspections/<int:pk>/',
         InspectionVisuelleViewSet.as_view({
             'get': 'retrieve', 'patch': 'partial_update', 'delete': 'destroy',
         }), name='inspections-detail'),
    path('api/inspections/<int:pk>/analyze/',
         InspectionVisuelleViewSet.as_view({'post': 'analyze'}),
         name='inspections-analyze'),

    # Swagger UI → http://localhost:8000/api/docs/
    path('api/schema/', SpectacularAPIView.as_view(), name='schema'),
    path('api/docs/',   SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
