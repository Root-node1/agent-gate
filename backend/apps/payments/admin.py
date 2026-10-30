from django.contrib import admin

from .models import CheckoutOrder, WebhookEvent


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


@admin.register(CheckoutOrder)
class CheckoutOrderAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "organization",
        "amount_minor",
        "currency",
        "status",
        "paypal_order_id",
        "paypal_capture_id",
        "idempotency_key",
        "capture_idempotency_key",
        "created_at",
        "updated_at",
    )
    list_filter = ("status", "currency", "organization")
    search_fields = ("paypal_order_id", "paypal_capture_id")
    readonly_fields = (
        "id",
        "organization",
        "amount_minor",
        "currency",
        "idempotency_key",
        "capture_idempotency_key",
        "paypal_order_id",
        "paypal_capture_id",
        "status",
        "created_at",
        "updated_at",
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
