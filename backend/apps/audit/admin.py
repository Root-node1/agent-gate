from django.contrib import admin

from .models import AuditEvent


@admin.register(AuditEvent)
class AuditEventAdmin(admin.ModelAdmin):
    list_display = ("created_at", "event_type", "actor_type", "agent", "spend_request")
    list_filter = ("event_type", "actor_type")
    readonly_fields = (
        "organization",
        "agent",
        "spend_request",
        "event_type",
        "actor_type",
        "actor_id",
        "payload",
        "prev_hash",
        "hash",
        "created_at",
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
