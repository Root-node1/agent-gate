from uuid import UUID

from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import status
from rest_framework.authentication import SessionAuthentication
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import Organization, OrgMembership
from apps.accounts.permissions import IsDashboardUser, IsOrganizationAdmin
from apps.common.errors import ApiError, ErrorCode
from apps.common.pagination import DashboardPagination
from apps.common.schema import error_responses

from .models import AuditEvent
from .serializers import AuditEventSerializer
from .services import AuditChainBroken, verify_organizations


def audit_queryset(user):
    return AuditEvent.objects.filter(
        organization__memberships__user=user
    ).select_related("organization")


class AuditListView(APIView):
    authentication_classes = [SessionAuthentication]
    permission_classes = [IsDashboardUser]

    @extend_schema(
        parameters=[
            OpenApiParameter("event_type", str, required=False),
            OpenApiParameter("agent", str, required=False),
            OpenApiParameter("spend_request", str, required=False),
            OpenApiParameter("after", int, required=False),
        ],
        responses={
            200: AuditEventSerializer(many=True),
            **error_responses(400, 401, 403, 429),
        },
        summary="List audit events for the caller's organizations",
    )
    def get(self, request):
        queryset = audit_queryset(request.user)
        event_type = request.query_params.get("event_type")
        if event_type:
            if event_type not in AuditEvent.EventType.values:
                raise ApiError(
                    "Unknown event_type.",
                    code=ErrorCode.VALIDATION_ERROR,
                    details={"event_type": ["Select a valid event type."]},
                )
            queryset = queryset.filter(event_type=event_type)
        for field in ("agent", "spend_request"):
            value = request.query_params.get(field)
            if not value:
                continue
            try:
                UUID(value)
            except ValueError as exc:
                raise ApiError(
                    f"{field} must be a UUID.",
                    code=ErrorCode.VALIDATION_ERROR,
                    details={field: ["Enter a valid UUID."]},
                ) from exc
            queryset = queryset.filter(**{f"{field}_id": value})
        after = request.query_params.get("after")
        if after is not None:
            try:
                after_id = int(after)
            except ValueError as exc:
                raise ApiError(
                    "after must be an integer event id.",
                    code=ErrorCode.VALIDATION_ERROR,
                    details={"after": ["Enter an integer event id."]},
                ) from exc
            queryset = queryset.filter(id__gt=after_id).order_by("id")
        paginator = DashboardPagination()
        page = paginator.paginate_queryset(queryset, request, view=self)
        return paginator.get_paginated_response(AuditEventSerializer(page, many=True).data)


class AuditVerifyView(APIView):
    authentication_classes = [SessionAuthentication]
    permission_classes = [IsOrganizationAdmin]

    @extend_schema(
        responses={200: dict, **error_responses(401, 403, 409, 429)},
        summary="Verify audit chains for administered organizations",
    )
    def get(self, request):
        organizations = Organization.objects.filter(
            memberships__user=request.user,
            memberships__role=OrgMembership.Role.ADMIN,
        ).distinct()
        try:
            checked = verify_organizations(organizations)
        except AuditChainBroken as exc:
            raise ApiError(
                str(exc),
                code=ErrorCode.AUDIT_CHAIN_BROKEN,
                status_code=status.HTTP_409_CONFLICT,
                details={
                    "organization": str(exc.organization_id),
                    "organization_name": exc.organization_name,
                    "event": exc.event_id,
                    "reason": exc.reason,
                },
            ) from exc
        return Response({"checked": checked, "organizations": organizations.count()})
