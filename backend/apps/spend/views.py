from django.shortcuts import get_object_or_404
from drf_spectacular.utils import (
    OpenApiExample,
    OpenApiParameter,
    OpenApiResponse,
    extend_schema,
)
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle
from rest_framework.views import APIView

from apps.accounts.permissions import IsDashboardUser
from apps.agents.authentication import (
    AgentKeyAuthentication,
    AgentPrincipal,
    DashboardSessionAuthentication,
    DemoModeAuthentication,
)
from apps.agents.throttling import AgentKeyRateThrottle, DemoModeRateThrottle
from apps.common.errors import ApiError, ErrorCode
from apps.common.pagination import DashboardPagination
from apps.common.query_params import (
    choice_param,
    datetime_param,
    ordering_param,
    uuid_param,
)
from apps.common.schema import error_responses

from . import pipeline
from .idempotency import key_is_valid
from .models import SpendRequest
from .serializers import SpendRequestCreateSerializer, SpendRequestSerializer

SPEND_ORDERING = (
    "id",
    "created_at",
    "updated_at",
    "amount_minor",
    "merchant_ref",
    "risk_score",
    "status",
    "decision",
)

SPEND_RESPONSE_EXAMPLE = OpenApiExample(
    "Needs approval",
    value={
        "id": "6f3f7f7e-5b0b-4d1f-9b0c-2f4f2f9d9c11",
        "amount": "125.00",
        "currency": "USD",
        "merchant": "acme.com",
        "purpose": "Replace the office printer",
        "source": "untrusted",
        "risk_score": 55,
        "decision": "needs_approval",
        "status": "pending_approval",
        "reasons": [{"code": "amount_over_threshold", "message": "Amount exceeds the approval threshold."}],
        "matched_rules": ["amount_over_threshold"],
        "paypal_reference": None,
        "created_at": "2026-11-04T12:00:00Z",
        "approval": "pending",
    },
    response_only=True,
)


def spend_queryset(user):
    """All spend requests belonging to organizations the caller is a member of."""
    return SpendRequest.objects.filter(
        organization__memberships__user=user
    ).select_related("approval")


class SpendRequestCreateView(APIView):
    authentication_classes = [AgentKeyAuthentication]
    throttle_classes = [AgentKeyRateThrottle, DemoModeRateThrottle, AnonRateThrottle]
    pagination_class = DashboardPagination

    def get_authenticators(self):
        if getattr(self.request, "method", None) == "GET":
            return [DemoModeAuthentication(), DashboardSessionAuthentication()]
        return super().get_authenticators()

    def get_permissions(self):
        if self.request.method == "GET":
            return [IsDashboardUser()]
        return super().get_permissions()

    @extend_schema(
        request=SpendRequestCreateSerializer,
        responses={
            201: OpenApiResponse(
                response=SpendRequestSerializer,
                examples=[SPEND_RESPONSE_EXAMPLE],
                description="The decision is in the body; always read `decision`.",
            ),
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
                source_type=SpendRequest.SourceType.UNTRUSTED,
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
        auth=[{"Session": []}],
        parameters=[
            OpenApiParameter("status", str, required=False),
            OpenApiParameter("decision", str, required=False),
            OpenApiParameter("agent", str, required=False),
            OpenApiParameter("created_after", str, required=False),
            OpenApiParameter("created_before", str, required=False),
            OpenApiParameter("from", str, required=False, description="Alias for created_after."),
            OpenApiParameter("to", str, required=False, description="Alias for created_before."),
            OpenApiParameter("ordering", str, required=False),
        ],
        responses={200: SpendRequestSerializer(many=True)},
        summary="List spend requests for the caller's organizations",
    )
    def get(self, request):
        queryset = spend_queryset(request.user)
        status_value = choice_param(request, "status", SpendRequest.Status)
        if status_value:
            queryset = queryset.filter(status=status_value)
        decision = choice_param(request, "decision", SpendRequest.Decision)
        if decision:
            queryset = queryset.filter(decision=decision)
        agent_id = uuid_param(request, "agent")
        if agent_id:
            queryset = queryset.filter(agent_id=agent_id)
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
        ordering = ordering_param(request, SPEND_ORDERING, ("-created_at", "-id"))
        if not any(field.lstrip("-") == "id" for field in ordering):
            ordering += ("-id",)
        queryset = queryset.order_by(*ordering)
        paginator = DashboardPagination()
        page = paginator.paginate_queryset(queryset, request, view=self)
        return paginator.get_paginated_response(SpendRequestSerializer(page, many=True).data)


class SpendRequestDetailView(APIView):
    authentication_classes = [
        AgentKeyAuthentication,
        DemoModeAuthentication,
        DashboardSessionAuthentication,
    ]
    permission_classes = [IsAuthenticated]
    throttle_classes = [AgentKeyRateThrottle, DemoModeRateThrottle]

    @extend_schema(
        auth=[{"AgentKey": []}, {"Session": []}],
        responses={
            200: OpenApiResponse(
                response=SpendRequestSerializer,
                examples=[SPEND_RESPONSE_EXAMPLE],
            ),
            **error_responses(401, 403, 404, 429),
        },
        summary="Get a spend request",
    )
    def get(self, request, pk):
        queryset = SpendRequest.objects.select_related("approval")
        if isinstance(request.user, AgentPrincipal):
            queryset = queryset.filter(agent=request.user.agent)
        else:
            queryset = queryset.filter(organization__memberships__user=request.user)
        spend_request = get_object_or_404(queryset, pk=pk)
        return Response(SpendRequestSerializer(spend_request).data)
