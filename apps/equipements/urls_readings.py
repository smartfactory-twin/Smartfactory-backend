"""
UC-13 — URL patterns for readings endpoints (add to equipements/urls.py)
"""
from django.urls import path
from . import views_readings

readings_urlpatterns = [
    # Historical readings + multi-sensor data
    path(
        "machines/<int:machine_id>/readings/",
        views_readings.ReadingsListView.as_view(),
        name="readings-list",
    ),
    # CSV export (UC-15)
    path(
        "machines/<int:machine_id>/readings/export/",
        views_readings.ReadingsExportCSVView.as_view(),
        name="readings-export-csv",
    ),
    # IoT gateway ingest
    path(
        "readings/",
        views_readings.ReadingCreateView.as_view(),
        name="reading-create",
    ),
]
