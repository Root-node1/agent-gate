from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import Organization, OrgMembership
from apps.accounts.permissions import IsDashboardUser, IsOrganizationAdmin
from apps.agents.authentication import (
    DashboardSessionAuthentication,
    DemoModeAuthentication,
)
from apps.agents.throttling import DemoModeRateThrottle
from apps.common.errors import ApiError, ErrorCode
from apps.common.pagination import DashboardPagination
from apps.common.query_params import (
    choice_param,
    datetime_param,
    ordering_param,
    uuid_param,
)
from apps.common.schema import error_responses

from .models import AuditEvent
from .serializers import AuditEventSerializer
from .services import AuditChainBroken, verify_organizations

AUDIT_ORDERING = ("id", "created_at", "event_type", "actor_type", "agent", "spend_request")
ACTOR_KINDS = {
    "person": (AuditEvent.ActorType.USER,),
    "agent": (AuditEvent.ActorType.AGENT,),
    "system": (AuditEvent.ActorType.SYSTEM, AuditEvent.ActorType.PAYPAL),
}


def audit_queryset(user):
    return AuditEvent.objects.filter(
        organization__memberships__user=user
    ).select_related("organization")


class AuditListView(APIView):
    authentication_classes = [DemoModeAuthentication, DashboardSessionAuthentication]
    permission_classes = [IsDashboardUser]
    throttle_classes = [DemoModeRateThrottle]

    @extend_schema(
        auth=[{"Session": []}],
        parameters=[
            OpenApiParameter("event_type", str, required=False),
            OpenApiParameter("agent", str, required=False),
            OpenApiParameter("spend_request", str, required=False),
            OpenApiParameter("actor", str, required=False),
            OpenApiParameter("actor_type", str, required=False),
            OpenApiParameter("actor_id", str, required=False),
            OpenApiParameter("created_after", str, required=False),
            OpenApiParameter("created_before", str, required=False),
            OpenApiParameter("from", str, required=False, description="Alias for created_after."),
            OpenApiParameter("to", str, required=False, description="Alias for created_before."),
            OpenApiParameter("after", int, required=False),
            OpenApiParameter("ordering", str, required=False),
        ],
        responses={
            200: AuditEventSerializer(many=True),
            **error_responses(400, 401, 403, 429),
        },
        summary="List audit events for the caller's organizations",
    )
    def get(self, request):
        queryset = audit_queryset(request.user)
        event_type = choice_param(request, "event_type", AuditEvent.EventType)
        if event_type:
            queryset = queryset.filter(event_type=event_type)
        for field in ("agent", "spend_request"):
            value = uuid_param(request, field)
            if value:
                queryset = queryset.filter(**{f"{field}_id": value})
        actor = choice_param(request, "actor", tuple(ACTOR_KINDS))
        if actor:
            queryset = queryset.filter(actor_type__in=ACTOR_KINDS[actor])
        actor_type = choice_param(request, "actor_type", AuditEvent.ActorType)
        if actor_type:
            queryset = queryset.filter(actor_type=actor_type)
        actor_id = request.query_params.get("actor_id")
        if actor_id:
            queryset = queryset.filter(actor_id=actor_id)
        created_after = datetime_param(
            request, "created_after"
        ) or datetime_param(request, "from")
        if created_after:
            queryset = queryset.filter(created_at__gte=created_after)
        created_before = datetime_param(
            request, "created_before", end_of_day=True
        ) or datetime_param(request, "to", end_of_day=True)
        if created_before:
            queryset = queryset.filter(created_at__lte=created_before)

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
        else:
            ordering = ordering_param(request, AUDIT_ORDERING, ("-created_at", "-id"))
            if not any(field.lstrip("-") == "id" for field in ordering):
                ordering += ("-id",)
            queryset = queryset.order_by(*ordering)

        paginator = DashboardPagination()
        page = paginator.paginate_queryset(queryset, request, view=self)
        return paginator.get_paginated_response(AuditEventSerializer(page, many=True).data)


class AuditVerifyView(APIView):
    authentication_classes = [DashboardSessionAuthentication]
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
