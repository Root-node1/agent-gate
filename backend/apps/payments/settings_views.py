"""Views for PayPal platform integration status and administrator probe.

Endpoints:
- GET /api/settings/paypal/status/
  - Authenticated via session.
  - Requires membership in at least one organization (IsDashboardUser).
  - Returns platform-wide connection status (not_configured, configured, successfully_tested, failed).
  - Never leaks secrets.

- POST /api/settings/paypal/probe/
  - Authenticated via session.
  - Requires active ADMIN role in user's organization (IsOrganizationAdmin).
  - Enforces verified MFA (MFAEnrollmentRequired / is_mfa_enabled).
  - Resolves organization strictly from authenticated user context (never trusts client input).
  - Enforces distributed rate limiting & circuit breaking via Redis.
  - Enforces strict overall 8.0-second deadline.
  - Records an immutable AuditEvent(event_type="integration.probed") with sanitized outcomes.
"""

from __future__ import annotations

import logging

from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import OrgMembership
from apps.accounts.permissions import IsDashboardUser, IsOrganizationAdmin
from apps.agents.authentication import DashboardSessionAuthentication
from apps.audit.models import AuditEvent
from apps.common.errors import ApiError, ErrorCode

from .paypal.probe_coordination import (
    CoordinationError,
    check_and_increment_probe_limits,
    record_probe_circuit_outcome,
)
from .paypal.probe_service import execute_sandbox_oauth_probe
from .paypal.probe_types import ProbeFailureReason
from .paypal.status_service import (
    get_platform_integration_status,
    update_platform_probe_outcome,
)

logger = logging.getLogger(__name__)


class PayPalSettingsStatusView(APIView):
    """Read-only view for platform PayPal Sandbox integration status."""

    authentication_classes = [DashboardSessionAuthentication]
    permission_classes = [IsDashboardUser]

    @extend_schema(
        summary="Get PayPal platform integration status",
        description="Returns platform-wide connection state and configuration flags without secrets.",
        responses={200: dict},
    )
    def get(self, request):
        status_data = get_platform_integration_status()
        return Response(status_data, status=status.HTTP_200_OK)


class PayPalSettingsProbeView(APIView):
    """Administrator-only endpoint to trigger a non-destructive Sandbox OAuth probe."""

    authentication_classes = [DashboardSessionAuthentication]
    permission_classes = [IsOrganizationAdmin]

    @extend_schema(
        request=None,
        summary="Probe PayPal Sandbox OAuth connectivity",
        description="Executes a backend-only OAuth 2.0 handshake against PayPal Sandbox.",
        responses={200: dict, 429: dict, 502: dict, 503: dict},
    )
    def post(self, request):
        # 1. Resolve active organization strictly from user's verified admin memberships
        # Never trust an arbitrary organization ID in the request payload
        admin_membership = (
            OrgMembership.objects.filter(
                user=request.user,
                role=OrgMembership.Role.ADMIN,
            )
            .select_related("organization")
            .first()
        )
        if not admin_membership:
            raise ApiError(
                "You must be an administrator of an organization to probe PayPal connectivity.",
                code=ErrorCode.PERMISSION_DENIED,
                status_code=status.HTTP_403_FORBIDDEN,
            )
        organization = admin_membership.organization

        # 2. Check distributed rate limits and circuit breaker in Redis (fails closed)
        try:
            coord_status = check_and_increment_probe_limits(str(organization.id))
        except CoordinationError as exc:
            logger.error("Distributed coordination failure during PayPal probe: %s", exc)
            return Response(
                {
                    "error": ProbeFailureReason.COORDINATION_UNAVAILABLE,
                    "message": "Distributed coordination is temporarily unavailable.",
                },
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        if not coord_status.allowed:
            reason = coord_status.rejection_reason
            if reason == ProbeFailureReason.CIRCUIT_OPEN:
                return Response(
                    {
                        "error": ProbeFailureReason.CIRCUIT_OPEN,
                        "message": (
                            "PayPal probe is temporarily throttled due to recent upstream failures. "
                            f"Try again in {coord_status.retry_after or 60} seconds."
                        ),
                        "retry_after": coord_status.retry_after or 60,
                    },
                    status=status.HTTP_503_SERVICE_UNAVAILABLE,
                )
            # Rate limited locally
            return Response(
                {
                    "error": ProbeFailureReason.RATE_LIMITED,
                    "message": "Probe rate limit exceeded. Please wait before retrying.",
                    "retry_after": coord_status.retry_after or 300,
                },
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )

        # 3. Execute upstream OAuth handshake (enforcing 8.0s overall deadline, 0 retries)
        probe_result = execute_sandbox_oauth_probe()

        # 4. Update circuit breaker tracking in Redis based on actual upstream outcome
        is_upstream_rate_limited = (probe_result.error_code == ProbeFailureReason.RATE_LIMITED)
        record_probe_circuit_outcome(
            success=probe_result.success,
            is_upstream_rate_limited=is_upstream_rate_limited,
        )

        # 5. Update platform-wide connection health in cache
        update_platform_probe_outcome(
            probe_result.success,
            tested_at=probe_result.tested_at,
            error_code=probe_result.error_code,
        )

        # 6. Record immutable AuditEvent attributing the initiating admin and organization
        try:
            AuditEvent.record(
                event_type=AuditEvent.EventType.INTEGRATION_PROBED,
                organization=organization,
                actor_type=AuditEvent.ActorType.USER,
                actor_id=str(request.user.id),
                success=probe_result.success,
                latency_ms=probe_result.latency_ms,
                error_code=probe_result.error_code,
            )
        except Exception as exc:
            logger.error("Failed to append audit event for PayPal probe: %s", exc)

        # 7. Format sanitized response
        if probe_result.success:
            return Response(
                {
                    "state": "successfully_tested",
                    "latency_ms": probe_result.latency_ms,
                    "tested_at": probe_result.tested_at,
                    "error": None,
                },
                status=status.HTTP_200_OK,
            )

        # Failed response
        status_code = status.HTTP_502_BAD_GATEWAY
        if probe_result.error_code == ProbeFailureReason.INVALID_CREDENTIALS:
            status_code = status.HTTP_400_BAD_REQUEST
        elif probe_result.error_code == ProbeFailureReason.RATE_LIMITED:
            status_code = status.HTTP_429_TOO_MANY_REQUESTS
        elif probe_result.error_code == ProbeFailureReason.TIMEOUT:
            status_code = status.HTTP_504_GATEWAY_TIMEOUT

        return Response(
            {
                "state": "failed",
                "latency_ms": probe_result.latency_ms,
                "tested_at": probe_result.tested_at,
                "error": probe_result.error_code,
            },
            status=status_code,
        )
