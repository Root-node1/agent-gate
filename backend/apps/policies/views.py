from uuid import UUID

from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import IsDashboardUser, IsOrganizationAdmin
from apps.agents.authentication import DashboardSessionAuthentication
from apps.common.pagination import DashboardPagination

from .models import Policy
from .serializers import PolicyCreateSerializer, PolicySerializer
from .services import PolicyConflictError, create_policy_version


class PolicyListView(APIView):
    authentication_classes = [DashboardSessionAuthentication]

    def get_permissions(self):
        if self.request.method == "POST":
            return [IsOrganizationAdmin()]
        return [IsDashboardUser()]

    @extend_schema(responses={200: PolicySerializer(many=True)}, summary="List policy versions")
    def get(self, request):
        queryset = (
            Policy.objects.filter(organization__memberships__user=request.user)
            .select_related("agent")
            .prefetch_related("merchant_rules")
        )
        agent = request.query_params.get("agent")
        if agent:
            try:
                UUID(agent)
            except ValueError:
                return Response(
                    {"detail": "agent must be a UUID."}, status=status.HTTP_400_BAD_REQUEST
                )
            queryset = queryset.filter(agent_id=agent)
        paginator = DashboardPagination()
        page = paginator.paginate_queryset(queryset, request, view=self)
        return paginator.get_paginated_response(PolicySerializer(page, many=True).data)

    @extend_schema(request=PolicyCreateSerializer, responses={201: PolicySerializer}, summary="Create a policy version")
    def post(self, request):
        serializer = PolicyCreateSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        try:
            policy = create_policy_version(
                user=request.user, validated=serializer.validated_data
            )
        except PolicyConflictError:
            return Response(
                {"detail": "Policy could not be created."}, status=status.HTTP_400_BAD_REQUEST
            )
        return Response(PolicySerializer(policy).data, status=status.HTTP_201_CREATED)
