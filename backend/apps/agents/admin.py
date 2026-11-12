from django.contrib import admin

from .models import Agent, ApiKey


class ApiKeyInline(admin.TabularInline):
    model = ApiKey
    extra = 0
    readonly_fields = tuple(field.name for field in ApiKey._meta.fields)

    def has_add_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Agent)
class AgentAdmin(admin.ModelAdmin):
    list_display = ("name", "organization", "status", "created_at")
    list_filter = ("status", "organization")
    readonly_fields = tuple(field.name for field in Agent._meta.fields)
    inlines = [ApiKeyInline]

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(ApiKey)
class ApiKeyAdmin(admin.ModelAdmin):
    list_display = ("prefix", "agent", "last_used_at", "revoked_at", "created_at")
    list_filter = ("revoked_at",)
    readonly_fields = tuple(field.name for field in ApiKey._meta.fields)

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
