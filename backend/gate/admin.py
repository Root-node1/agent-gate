from django.contrib import admin

from .models import Agent, Approval, AuditEvent, MerchantRule, Policy, SpendRequest


@admin.register(Agent)
class AgentAdmin(admin.ModelAdmin):
    list_display = ("name", "status", "api_key_prefix", "created_at")
    readonly_fields = ("api_key_prefix", "api_key_hash", "created_at")

    def has_add_permission(self, request):
        # Agents are created with Agent.create_with_key() so the key is hashed.
        return False


class MerchantRuleInline(admin.TabularInline):
    model = MerchantRule
    extra = 0


@admin.register(Policy)
class PolicyAdmin(admin.ModelAdmin):
    list_display = ("agent", "currency", "per_transaction_cap", "approval_threshold", "daily_budget", "monthly_budget")
    inlines = [MerchantRuleInline]


@admin.register(SpendRequest)
class SpendRequestAdmin(admin.ModelAdmin):
    list_display = ("created_at", "agent", "amount", "currency", "merchant", "decision", "risk_score")
    list_filter = ("decision", "source")
    search_fields = ("merchant", "purpose")


@admin.register(Approval)
class ApprovalAdmin(admin.ModelAdmin):
    list_display = ("spend_request", "outcome", "approver", "decided_at")
    list_filter = ("outcome",)


@admin.register(AuditEvent)
class AuditEventAdmin(admin.ModelAdmin):
    list_display = ("created_at", "event_type", "agent", "spend_request")
    list_filter = ("event_type",)
    readonly_fields = ("event_type", "agent", "spend_request", "payload", "created_at")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
