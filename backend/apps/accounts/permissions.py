"""Role checks and organization scoping for dashboard principals."""

from rest_framework.exceptions import NotAuthenticated
from rest_framework.permissions import BasePermission

from .models import OrgMembership

APPROVER_ROLES = (OrgMembership.Role.ADMIN, OrgMembership.Role.APPROVER)


def membership_exists(user, *, roles=None) -> bool:
    if not user or not user.is_authenticated:
        return False
    memberships = user.memberships.all()
    if roles is not None:
        memberships = memberships.filter(role__in=roles)
    return memberships.exists()


class IsDashboardUser(BasePermission):
    """Any authenticated user with at least one organization membership."""

    def has_permission(self, request, view):
        return membership_exists(request.user)


class IsApprover(BasePermission):
    """A dashboard user who may approve or deny requests in at least one organization."""

    def has_permission(self, request, view):
        return membership_exists(request.user, roles=APPROVER_ROLES)


class IsOrganizationAdmin(BasePermission):
    """A dashboard user with the admin role in at least one organization."""

    def has_permission(self, request, view):
        return membership_exists(request.user, roles=(OrgMembership.Role.ADMIN,))


class IsAuthenticatedOr401(BasePermission):
    """
    Return 401 Unauthenticated for unauthenticated requests,
    403 Forbidden for authenticated but unauthorized requests.
    """

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            raise NotAuthenticated()
        return True