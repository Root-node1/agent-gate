from django.contrib import admin

from .models import SpendRequest


@admin.register(SpendRequest)
class SpendRequestAdmin(admin.ModelAdmin):
    list_display = ("created_at", "agent", "amount_minor", "currency", "merchant_ref", "decision", "status", "risk_score")
    list_filter = ("decision", "status", "source_type")
    search_fields = ("merchant_ref", "purpose")
    readonly_fields = ("id", "created_at", "updated_at")
