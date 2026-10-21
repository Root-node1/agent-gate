from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import Organization, OrgMembership, User


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
