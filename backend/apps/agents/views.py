"""Agent management views for the dashboard."""

from django.db import IntegrityError, transaction
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import Organization
from apps.accounts.permissions import IsDashboardUser, IsOrganizationAdmin
from apps.audit.models import AuditEvent
from apps.common.pagination import DashboardPagination

from .authentication import DashboardSessionAuthentication
from .models import Agent
from .serializers import AgentCreateSerializer, AgentSerializer, AgentUpdateSerializer


def agent_queryset(user):
    """All agents belonging to organizations the caller is a member of."""
    return Agent.objects.filter(
        organization__memberships__user=user
    ).select_related("organization").prefetch_related("api_keys", "policies")


@extend_schema(tags=["agents"])
class AgentListView(APIView):
    """GET /v1/agents/ — list ; POST /v1/agents/ — create"""

    authentication_classes = [DashboardSessionAuthentication]

    def get_permissions(self):
        if self.request.method == "POST":
            return [IsOrganizationAdmin()]
        return [IsDashboardUser()]

    @extend_schema(responses={200: AgentSerializer(many=True)})
    def get(self, request):
        queryset = agent_queryset(request.user)
        paginator = DashboardPagination()
        page = paginator.paginate_queryset(queryset, request, view=self)
        serializer = AgentSerializer(page, many=True, context={"list_view": True})
        return paginator.get_paginated_response(serializer.data)

    @extend_schema(request=AgentCreateSerializer, responses={201: AgentSerializer})
    def post(self, request):
        serializer = AgentCreateSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)

        name = serializer.validated_data["name"]
        org_id = serializer.validated_data["organization"]
        organization = get_object_or_404(Organization, pk=org_id)

        with transaction.atomic():
            if Agent.objects.filter(name=name, organization_id=org_id).exists():
                return Response(
                    {"detail": "An agent with this name already exists in this organization."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            try:
                agent, raw_key = Agent.create_with_key(name, organization)
            except IntegrityError:
                return Response(
                    {"detail": "An agent with this name already exists in this organization."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            key = agent.current_key
            AuditEvent.record(
                AuditEvent.EventType.AGENT_CREATED,
                organization=organization,
                agent=agent,
                actor_type=AuditEvent.ActorType.USER,
                actor_id=str(request.user.id),
                name=name,
            )
            AuditEvent.record(
                AuditEvent.EventType.KEY_CREATED,
                organization=organization,
                agent=agent,
                actor_type=AuditEvent.ActorType.USER,
                actor_id=str(request.user.id),
                prefix=key.prefix if key else None,
            )

        return Response(
            {
                "id": str(agent.id),
                "name": agent.name,
                "organization": str(agent.organization_id),
                "status": agent.status,
                "created_at": agent.created_at,
                "updated_at": agent.updated_at,
                "api_key": raw_key,
            },
            status=status.HTTP_201_CREATED,
        )


@extend_schema(tags=["agents"])
class AgentDetailView(APIView):
    """GET /v1/agents/{id}/ — retrieve ; PATCH /v1/agents/{id}/ — update"""

    authentication_classes = [DashboardSessionAuthentication]

    def get_permissions(self):
        if self.request.method == "PATCH":
            return [IsOrganizationAdmin()]
        return [IsDashboardUser()]

    @extend_schema(responses={200: AgentSerializer})
    def get(self, request, pk):
        agent = get_object_or_404(agent_queryset(request.user), pk=pk)
        serializer = AgentSerializer(agent)
        return Response(serializer.data)

    @extend_schema(request=AgentUpdateSerializer, responses={200: AgentSerializer})
    def patch(self, request, pk):
        agent = get_object_or_404(agent_queryset(request.user), pk=pk)
        old_name = agent.name
        old_status = agent.status

        serializer = AgentUpdateSerializer(agent, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)

        with transaction.atomic():
            serializer.save()
            validated = serializer.validated_data

            if "name" in validated and validated["name"] != old_name:
                AuditEvent.record(
                    AuditEvent.EventType.AGENT_UPDATED,
                    organization=agent.organization,
                    agent=agent,
                    actor_type=AuditEvent.ActorType.USER,
                    actor_id=str(request.user.id),
                    field="name",
                    old_value=old_name,
                    new_value=validated["name"],
                )

            if "status" in validated and validated["status"] != old_status:
                AuditEvent.record(
                    AuditEvent.EventType.AGENT_SUSPENDED,
                    organization=agent.organization,
                    agent=agent,
                    actor_type=AuditEvent.ActorType.USER,
                    actor_id=str(request.user.id),
                    from_status=old_status,
                    to_status=validated["status"],
                )

        agent.refresh_from_db()
        return Response(AgentSerializer(agent).data)


@extend_schema(tags=["agents"])
class AgentRotateKeyView(APIView):
    authentication_classes = [DashboardSessionAuthentication]
    permission_classes = [IsOrganizationAdmin]

    @extend_schema(responses={200: dict, 400: dict})
    def post(self, request, pk):
        agent = get_object_or_404(agent_queryset(request.user), pk=pk)
        old_key = agent.current_key
        old_prefix = old_key.prefix if old_key else None

        with transaction.atomic():
            new_key, raw_key = agent.rotate_key()

            AuditEvent.record(
                AuditEvent.EventType.KEY_REVOKED,
                organization=agent.organization,
                agent=agent,
                actor_type=AuditEvent.ActorType.USER,
                actor_id=str(request.user.id),
                prefix=old_prefix,
            )
            AuditEvent.record(
                AuditEvent.EventType.KEY_CREATED,
                organization=agent.organization,
                agent=agent,
                actor_type=AuditEvent.ActorType.USER,
                actor_id=str(request.user.id),
                prefix=new_key.prefix,
            )

        current = agent.current_key
        return Response(
            {
                "id": str(agent.id),
                "name": agent.name,
                "status": agent.status,
                "current_key": (
                    {
                        "prefix": current.prefix,
                        "created_at": current.created_at,
                        "last_used_at": current.last_used_at,
                    }
                    if current
                    else None
                ),
                "api_key": raw_key,
            }
        )


@extend_schema(tags=["agents"])
class AgentRevokeKeyView(APIView):
    authentication_classes = [DashboardSessionAuthentication]
    permission_classes = [IsOrganizationAdmin]

    @extend_schema(responses={200: dict, 400: dict})
    def post(self, request, pk):
        agent = get_object_or_404(agent_queryset(request.user), pk=pk)
        revoked_key = agent.revoke_current_key()

        if revoked_key is None:
            return Response(
                {"detail": "No active API key to revoke."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        with transaction.atomic():
            AuditEvent.record(
                AuditEvent.EventType.KEY_REVOKED,
                organization=agent.organization,
                agent=agent,
                actor_type=AuditEvent.ActorType.USER,
                actor_id=str(request.user.id),
                prefix=revoked_key.prefix,
                revoked_at=revoked_key.revoked_at,
            )

        return Response(
            {
                "id": str(agent.id),
                "name": agent.name,
                "status": agent.status,
                "current_key": None,
                "revoked_key": {
                    "prefix": revoked_key.prefix,
                    "revoked_at": revoked_key.revoked_at,
                },
            }
        )
