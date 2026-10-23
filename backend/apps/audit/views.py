from uuid import UUID

from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import status
from rest_framework.authentication import SessionAuthentication
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import Organization, OrgMembership
from apps.accounts.permissions import IsDashboardUser, IsOrganizationAdmin
from apps.common.pagination import DashboardPagination

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
        responses={200: AuditEventSerializer(many=True)},
        summary="List audit events for the caller's organizations",
    )
    def get(self, request):
        queryset = audit_queryset(request.user)
        event_type = request.query_params.get("event_type")
        if event_type:
            if event_type not in AuditEvent.EventType.values:
                return Response(
                    {"detail": "Unknown event_type."}, status=status.HTTP_400_BAD_REQUEST
                )
            queryset = queryset.filter(event_type=event_type)
        for field in ("agent", "spend_request"):
            value = request.query_params.get(field)
            if not value:
                continue
            try:
                UUID(value)
            except ValueError:
                return Response(
                    {"detail": f"{field} must be a UUID."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            queryset = queryset.filter(**{f"{field}_id": value})
        after = request.query_params.get("after")
        if after is not None:
            try:
                after_id = int(after)
            except ValueError:
                return Response(
                    {"detail": "after must be an integer event id."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            queryset = queryset.filter(id__gt=after_id).order_by("id")
        paginator = DashboardPagination()
        page = paginator.paginate_queryset(queryset, request, view=self)
        return paginator.get_paginated_response(AuditEventSerializer(page, many=True).data)


class AuditVerifyView(APIView):
    authentication_classes = [SessionAuthentication]
    permission_classes = [IsOrganizationAdmin]

    @extend_schema(responses={200: dict}, summary="Verify audit chains for administered organizations")
    def get(self, request):
        organizations = Organization.objects.filter(
            memberships__user=request.user,
            memberships__role=OrgMembership.Role.ADMIN,
        ).distinct()
        try:
            checked = verify_organizations(organizations)
        except AuditChainBroken as exc:
            return Response(
                {
                    "detail": str(exc),
                    "organization": str(exc.organization_id),
                    "organization_name": exc.organization_name,
                    "event": exc.event_id,
                    "reason": exc.reason,
                },
                status=status.HTTP_409_CONFLICT,
            )
        return Response({"checked": checked, "organizations": organizations.count()})
