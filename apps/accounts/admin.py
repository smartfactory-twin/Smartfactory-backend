from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import AuditLog, Utilisateur


@admin.register(Utilisateur)
class UtilisateurAdmin(BaseUserAdmin):
    list_display = ['email', 'nom', 'prenom', 'role', 'actif', 'date_joined']
    list_filter = ['role', 'actif']
    search_fields = ['email', 'nom', 'prenom']
    ordering = ['-date_joined']

    fieldsets = (
        (None, {'fields': ('email', 'password')}),
        ('Informations personnelles', {'fields': ('nom', 'prenom')}),
        ('Permissions', {'fields': ('role', 'actif', 'is_staff', 'is_superuser', 'groups', 'user_permissions')}),
        ('Dates importantes', {'fields': ('last_login', 'date_joined')}),
    )
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('email', 'nom', 'prenom', 'role', 'password1', 'password2'),
        }),
    )


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ('cree_le', 'acteur_email', 'acteur_role', 'action', 'code_http', 'adresse_ip')
    list_filter = ('methode', 'code_http', 'acteur_role')
    search_fields = ('acteur_email', 'action', 'chemin')
    readonly_fields = tuple(field.name for field in AuditLog._meta.fields)
    date_hierarchy = 'cree_le'

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
