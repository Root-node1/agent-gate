from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import AccountProfile, Organization, OrgMembership, User


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    pass


@admin.register(Organization)
class OrganizationAdmin(admin.ModelAdmin):
    list_display = ("name", "created_at")
    search_fields = ("name",)


@admin.register(OrgMembership)
class OrgMembershipAdmin(admin.ModelAdmin):
    list_display = ("user", "organization", "role", "created_at")
    list_filter = ("role", "organization")
    search_fields = ("user__username", "organization__name")


@admin.register(AccountProfile)
class AccountProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "full_name")
    search_fields = ("user__username", "full_name", "user__email")
    raw_id_fields = ("user",)
