from uuid import UUID

from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.authentication import SessionAuthentication
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import IsDashboardUser
from apps.common.pagination import DashboardPagination

from .models import Policy
from .serializers import PolicySerializer


class PolicyListView(APIView):
    authentication_classes = [SessionAuthentication]
    permission_classes = [IsDashboardUser]

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
