from django.contrib import admin

from .models import Approval


@admin.register(Approval)
class ApprovalAdmin(admin.ModelAdmin):
    list_display = ("spend_request", "outcome", "approver", "requested_at", "expires_at", "decided_at")
    list_filter = ("outcome",)
