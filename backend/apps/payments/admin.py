from django.contrib import admin

from .models import WebhookEvent


@admin.register(WebhookEvent)
class WebhookEventAdmin(admin.ModelAdmin):
    list_display = ("paypal_event_id", "event_type", "signature_verified", "received_at", "processed_at")
    list_filter = ("event_type", "signature_verified")
    readonly_fields = (
        "paypal_event_id",
        "event_type",
        "payload",
        "signature_verified",
        "received_at",
        "processed_at",
        "created_at",
        "updated_at",
    )

    def has_add_permission(self, request):
        return False
