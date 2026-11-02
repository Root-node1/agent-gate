from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle
from rest_framework.views import APIView

from apps.accounts.permissions import IsDashboardUser
from apps.agents.authentication import (
    AgentKeyAuthentication,
    DashboardSessionAuthentication,
)
from apps.agents.throttling import AgentKeyRateThrottle
from apps.common.errors import ApiError, ErrorCode
from apps.common.pagination import DashboardPagination
from apps.common.schema import error_responses

from . import pipeline
from .idempotency import key_is_valid
from .models import SpendRequest
from .serializers import SpendRequestCreateSerializer, SpendRequestSerializer


def spend_queryset(user):
    """All spend requests belonging to organizations the caller is a member of."""
    return (
        SpendRequest.objects.filter(organization__memberships__user=user)
        .select_related("approval")
        .order_by("-created_at", "-id")
    )


class SpendRequestCreateView(APIView):
    authentication_classes = [AgentKeyAuthentication]
    throttle_classes = [AgentKeyRateThrottle, AnonRateThrottle]
    pagination_class = DashboardPagination

    def get_authenticators(self):
        if getattr(self.request, "method", None) == "GET":
            return [DashboardSessionAuthentication()]
        return super().get_authenticators()

    def get_permissions(self):
        if self.request.method == "GET":
            return [IsDashboardUser()]
        return super().get_permissions()

    @extend_schema(
        request=SpendRequestCreateSerializer,
        responses={
            201: SpendRequestSerializer,
            **error_responses(400, 401, 403, 409, 429),
        },
        summary="Submit a spend request",
        description=(
            "Returns 201 with the firewall's decision in the body: allow, deny or needs_approval. "
            "Always read `decision`; the status code alone does not mean the payment is allowed."
        ),
    )
    def post(self, request):
        idempotency_key = request.headers.get("Idempotency-Key", "").strip()
        if not key_is_valid(idempotency_key):
            raise ApiError(
                "A valid Idempotency-Key header is required.",
                code=ErrorCode.IDEMPOTENCY_KEY_REQUIRED,
                details={
                    "idempotency_key": [
                        "Use 1-255 printable characters in the Idempotency-Key header."
                    ]
                },
            )

        serializer = SpendRequestCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            spend_request, replayed = pipeline.submit_spend_request(
                request.user.agent,
                idempotency_key=idempotency_key,
                **serializer.validated_data,
            )
        except pipeline.PolicyMissing as exc:
            raise ApiError(
                "This agent has no policy configured.",
                code=ErrorCode.POLICY_MISSING,
                status_code=status.HTTP_409_CONFLICT,
            ) from exc
        except pipeline.IdempotencyConflict as exc:
            raise ApiError(
                "Idempotency-Key was reused with a different request.",
                code=ErrorCode.IDEMPOTENCY_CONFLICT,
                status_code=status.HTTP_409_CONFLICT,
            ) from exc
        response = Response(
            SpendRequestSerializer(spend_request).data, status=status.HTTP_201_CREATED
        )
        if replayed:
            response["Idempotent-Replayed"] = "true"
        return response

    @extend_schema(
        responses={200: SpendRequestSerializer(many=True)},
        summary="List spend requests for the caller's organizations",
    )
    def get(self, request):
        queryset = spend_queryset(request.user)
        paginator = DashboardPagination()
        page = paginator.paginate_queryset(queryset, request, view=self)
        return paginator.get_paginated_response(SpendRequestSerializer(page, many=True).data)


class SpendRequestDetailView(APIView):
    authentication_classes = [AgentKeyAuthentication]
    throttle_classes = [AgentKeyRateThrottle, AnonRateThrottle]

    @extend_schema(
        responses={200: SpendRequestSerializer, **error_responses(401, 403, 404, 429)},
        summary="Get a spend request",
    )
    def get(self, request, pk):
        spend_request = get_object_or_404(
            SpendRequest.objects.select_related("approval"),
            pk=pk,
            agent=request.user.agent,
        )
        return Response(SpendRequestSerializer(spend_request).data)
