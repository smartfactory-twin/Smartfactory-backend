from django.contrib import admin
from .models import (
    Usine, Zone, LigneProduction, Machine, Document, Composant, Sensor, Reading,
    InspectionVisuelle,
)

@admin.register(Usine)
class UsineAdmin(admin.ModelAdmin):
    list_display = ['nom', 'adresse', 'created_at']

@admin.register(Zone)
class ZoneAdmin(admin.ModelAdmin):
    list_display = ['nom', 'usine']
    list_filter = ['usine']

@admin.register(LigneProduction)
class LigneProductionAdmin(admin.ModelAdmin):
    list_display = ['nom', 'zone']
    list_filter = ['zone__usine']

@admin.register(Machine)
class MachineAdmin(admin.ModelAdmin):
    list_display = ['nom', 'identifiant_interne', 'statut', 'ligne_production', 'date_installation']
    list_filter = ['statut', 'ligne_production__zone__usine']
    search_fields = ['nom', 'identifiant_interne', 'numero_serie']

@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    list_display = ['nom', 'type_document', 'machine', 'created_at']

@admin.register(Composant)
class ComposantAdmin(admin.ModelAdmin):
    list_display = ['nom', 'machine', 'numero_piece']


# ── Module 3 — Capteurs & Données IoT ─────────────────────────────────────────

@admin.register(Sensor)
class SensorAdmin(admin.ModelAdmin):
    list_display = ['identifiant', 'nom', 'type_capteur', 'machine', 'unite', 'actif']
    list_filter = ['type_capteur', 'actif', 'machine__ligne_production__zone__usine']
    search_fields = ['identifiant', 'nom', 'machine__nom', 'machine__identifiant_interne']


@admin.register(Reading)
class ReadingAdmin(admin.ModelAdmin):
    list_display = ['sensor', 'valeur', 'timestamp', 'hors_plage', 'est_valide', 'interpolation']
    list_filter = ['hors_plage', 'est_valide', 'interpolation']
    search_fields = ['sensor__identifiant']
    date_hierarchy = 'timestamp'


# ── Module 4 — Inspections visuelles par IA ───────────────────────────────────

@admin.register(InspectionVisuelle)
class InspectionVisuelleAdmin(admin.ModelAdmin):
    list_display = ['id', 'machine', 'utilisateur', 'statut_analyse',
                    'score_confiance', 'date_inspection']
    list_filter = ['statut_analyse', 'machine__ligne_production__zone__usine']
    search_fields = ['machine__nom', 'machine__identifiant_interne']
    date_hierarchy = 'date_inspection'
