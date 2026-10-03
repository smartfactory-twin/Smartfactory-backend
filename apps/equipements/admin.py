from django.contrib import admin
from .models import Usine, Zone, LigneProduction, Machine, Document, Composant

@admin.register(Usine)
class UsineAdmin(admin.ModelAdmin):
    list_display = ['nom', 'adresse', 'created_at']
    search_fields = ['nom']

@admin.register(Zone)
class ZoneAdmin(admin.ModelAdmin):
    list_display = ['nom', 'usine']
    list_filter = ['usine']
    search_fields = ['nom']

@admin.register(LigneProduction)
class LigneProductionAdmin(admin.ModelAdmin):
    list_display = ['nom', 'zone']
    list_filter = ['zone__usine']
    search_fields = ['nom']

@admin.register(Machine)
class MachineAdmin(admin.ModelAdmin):
    list_display = ['nom', 'identifiant_interne', 'statut', 'ligne_production', 'created_at']
    list_filter = ['statut', 'ligne_production__zone__usine']
    search_fields = ['nom', 'identifiant_interne', 'numero_serie']

@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    list_display = ['nom', 'type_document', 'machine', 'created_at']
    list_filter = ['type_document']

@admin.register(Composant)
class ComposantAdmin(admin.ModelAdmin):
    list_display = ['nom', 'machine', 'numero_piece']
    search_fields = ['nom', 'numero_piece']
