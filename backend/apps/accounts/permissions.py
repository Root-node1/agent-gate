"""Role checks and organization scoping for dashboard principals."""

from allauth.mfa.utils import is_mfa_enabled
from rest_framework.exceptions import NotAuthenticated, PermissionDenied
from rest_framework.permissions import BasePermission

from apps.agents.authentication import AgentPrincipal

from .models import OrgMembership

APPROVER_ROLES = (OrgMembership.Role.ADMIN, OrgMembership.Role.APPROVER)

MFA_ENROLLMENT_REQUIRED_CODE = "mfa_enrollment_required"


def membership_exists(user, *, roles=None) -> bool:
    if not user or not user.is_authenticated:
        return False
    memberships = user.memberships.all()
    if roles is not None:
        memberships = memberships.filter(role__in=roles)
    return memberships.exists()


class IsMFAEnforced(BasePermission):
    """Reject unauthenticated and machine principals (401).

    First gate in the privileged-permission evaluation chain.  Only
    session-authenticated human users (not ``AnonymousUser`` or
    ``AgentPrincipal``) may proceed to the role check and the
    MFA-enrollment check.
    """

    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated:
            raise NotAuthenticated()
        if isinstance(user, AgentPrincipal):
            raise NotAuthenticated()
        return True


class MFAEnrollmentRequired(BasePermission):
    """Require an enrolled MFA authenticator for the authenticated user.

    Raises 403 with ``code: "mfa_enrollment_required"`` when the user is
    authenticated but has not enrolled in MFA.  Used by ``IsApprover`` and
    ``IsOrganizationAdmin`` to enforce mandatory TOTP enrollment for
    privileged roles (``IsDashboardUser`` / viewers are unaffected).
    """

    def has_permission(self, request, view):
        if is_mfa_enabled(request.user):
            return True
        raise PermissionDenied(
            detail={
                "code": MFA_ENROLLMENT_REQUIRED_CODE,
                "detail": "MFA enrollment is required for this role.",
            },
            code=MFA_ENROLLMENT_REQUIRED_CODE,
        )


class IsDashboardUser(BasePermission):
    """Any authenticated user with at least one organization membership."""

    def has_permission(self, request, view):
        return membership_exists(request.user)


class IsApprover(BasePermission):
    """A dashboard user who may approve or deny requests in at least one organization.

    Evaluation order:
      1. Reject unauthenticated and machine principals (``IsMFAEnforced`` → 401).
      2. Verify the existing approver/admin organization role.
      3. Require MFA enrollment (``MFAEnrollmentRequired`` → 403 mfa_enrollment_required).
    """

    def has_permission(self, request, view):
        if not IsMFAEnforced().has_permission(request, view):
            return False
        if not membership_exists(request.user, roles=APPROVER_ROLES):
            return False
        return MFAEnrollmentRequired().has_permission(request, view)


class IsOrganizationAdmin(BasePermission):
    """A dashboard user with the admin role in at least one organization.

    Evaluation order:
      1. Reject unauthenticated and machine principals (``IsMFAEnforced`` → 401).
      2. Verify the existing admin organization role.
      3. Require MFA enrollment (``MFAEnrollmentRequired`` → 403 mfa_enrollment_required).
    """

    def has_permission(self, request, view):
        if not IsMFAEnforced().has_permission(request, view):
            return False
        if not membership_exists(request.user, roles=(OrgMembership.Role.ADMIN,)):
            return False
        return MFAEnrollmentRequired().has_permission(request, view)


class IsAuthenticatedOr401(BasePermission):
    """
    Return 401 Unauthenticated for unauthenticated requests,
    403 Forbidden for authenticated but unauthorized requests.
    """

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            raise NotAuthenticated()
        return True