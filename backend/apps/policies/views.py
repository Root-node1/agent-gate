from uuid import UUID

from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import IsDashboardUser, IsOrganizationAdmin
from apps.agents.authentication import DashboardSessionAuthentication
from apps.common.pagination import DashboardPagination

from .models import Policy
from .serializers import (
    MerchantRuleCreateSerializer,
    PolicyCreateSerializer,
    PolicySerializer,
    PolicyUpdateSerializer,
)
from .services import (
    PolicyConflictError,
    PolicyValidationError,
    add_merchant_rule,
    create_policy_update,
    create_policy_version,
    remove_merchant_rule,
)


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
        return Response(
            PolicySerializer(policy).data, status=status.HTTP_201_CREATED
        )


@extend_schema(tags=["policies"])
class PolicyDetailView(APIView):
    """GET /v1/policies/{id}/ — retrieve ; PATCH /v1/policies/{id}/ — new version"""

    authentication_classes = [DashboardSessionAuthentication]

    def get_permissions(self):
        if self.request.method == "PATCH":
            return [IsOrganizationAdmin()]
        return [IsDashboardUser()]

    def get_queryset(self, user):
        """Policies in organizations the caller belongs to (404 for foreign)."""
        return (
            Policy.objects.filter(organization__memberships__user=user)
            .select_related("agent")
            .prefetch_related("merchant_rules")
        )

    @extend_schema(responses={200: PolicySerializer}, summary="Retrieve a policy version")
    def get(self, request, pk):
        policy = get_object_or_404(self.get_queryset(request.user), pk=pk)
        return Response(PolicySerializer(policy).data)

    @extend_schema(
        request=PolicyUpdateSerializer, responses={200: PolicySerializer}, summary="Update a policy (new version)"
    )
    def patch(self, request, pk):
        serializer = PolicyUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            policy = create_policy_update(
                user=request.user, policy_id=pk, validated=serializer.validated_data
            )
        except PolicyConflictError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
        except PolicyValidationError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(PolicySerializer(policy).data, status=status.HTTP_200_OK)


@extend_schema(tags=["policies"])
class MerchantRuleCreateView(APIView):
    """POST /v1/policies/{id}/merchant-rules/ — append one rule, new version"""

    authentication_classes = [DashboardSessionAuthentication]
    permission_classes = [IsOrganizationAdmin]

    @extend_schema(
        request=MerchantRuleCreateSerializer,
        responses={201: PolicySerializer},
        summary="Add a merchant rule (new policy version)",
    )
    def post(self, request, pk):
        serializer = MerchantRuleCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            policy = add_merchant_rule(
                user=request.user, policy_id=pk, validated=serializer.validated_data
            )
        except PolicyConflictError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
        except PolicyValidationError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(
            PolicySerializer(policy).data, status=status.HTTP_201_CREATED
        )


@extend_schema(tags=["policies"])
class MerchantRuleDeleteView(APIView):
    """DELETE /v1/policies/{id}/merchant-rules/{rule_id}/ — new version without rule"""

    authentication_classes = [DashboardSessionAuthentication]
    permission_classes = [IsOrganizationAdmin]

    @extend_schema(
        responses={200: PolicySerializer},
        summary="Remove a merchant rule (new policy version)",
    )
    def delete(self, request, pk, rule_id):
        expected_version = _parse_if_match(request)
        if expected_version is None:
            return Response(
                {
                    "detail": "Missing expected-version concurrency token; "
                    "send the latest policy version in the If-Match header."
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            policy = remove_merchant_rule(
                user=request.user,
                policy_id=pk,
                rule_id=rule_id,
                expected_version=expected_version,
            )
        except PolicyConflictError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
        except PolicyValidationError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(
            PolicySerializer(policy).data, status=status.HTTP_200_OK
        )


def _parse_if_match(request) -> int | None:
    """Extract the expected-version integer from the If-Match header.

    The header carries a bare integer (the caller's expected latest policy
    version).  Quoted forms such as ``"1"`` are also accepted.
    """
    raw = request.META.get("HTTP_IF_MATCH", "")
    if not raw:
        return None
    cleaned = raw.strip().strip('"').strip("'")
    try:
        value = int(cleaned)
    except ValueError:
        return None
    if value < 1:
        return None
    return value
