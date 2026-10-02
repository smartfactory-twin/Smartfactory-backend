from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display  = ['email', 'username', 'get_full_name', 'role', 'is_active', 'date_joined']
    list_filter   = ['role', 'is_active']
    search_fields = ['email', 'username', 'first_name', 'last_name']
    ordering      = ['-date_joined']

    fieldsets = BaseUserAdmin.fieldsets + (
        ('Rôle & Contact', {'fields': ('role', 'phone', 'avatar')}),
    )
    add_fieldsets = BaseUserAdmin.add_fieldsets + (
        ('Rôle & Contact', {'fields': ('email', 'role', 'phone')}),
    )
