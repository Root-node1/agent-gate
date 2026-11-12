from django.contrib import admin

from .models import MerchantRule, Policy


class MerchantRuleInline(admin.TabularInline):
    model = MerchantRule
    extra = 0
    readonly_fields = tuple(field.name for field in MerchantRule._meta.fields)

    def has_add_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Policy)
class PolicyAdmin(admin.ModelAdmin):
    list_display = (
        "agent",
        "version",
        "currency",
        "per_transaction_cap_minor",
        "daily_budget_minor",
        "weekly_budget_minor",
        "monthly_budget_minor",
    )
    list_filter = ("currency", "merchant_mode")
    readonly_fields = tuple(field.name for field in Policy._meta.fields)
    inlines = [MerchantRuleInline]

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(MerchantRule)
class MerchantRuleAdmin(admin.ModelAdmin):
    list_display = ("policy", "merchant_ref", "kind")
    list_filter = ("kind",)
    search_fields = ("merchant_ref",)
    readonly_fields = tuple(field.name for field in MerchantRule._meta.fields)

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
