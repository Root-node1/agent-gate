from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle
from rest_framework.views import APIView

from apps.agents.authentication import AgentKeyAuthentication
from apps.agents.throttling import AgentKeyRateThrottle
from apps.common.errors import ApiError, ErrorCode
from apps.common.schema import error_responses

from . import services
from .idempotency import key_is_valid
from .models import SpendRequest
from .serializers import SpendRequestCreateSerializer, SpendRequestSerializer


class SpendRequestCreateView(APIView):
    authentication_classes = [AgentKeyAuthentication]
    throttle_classes = [AgentKeyRateThrottle, AnonRateThrottle]

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
            spend_request, replayed = services.submit_spend_request(
                request.user.agent,
                idempotency_key=idempotency_key,
                **serializer.validated_data,
            )
        except services.PolicyMissing as exc:
            raise ApiError(
                "This agent has no policy configured.",
                code=ErrorCode.POLICY_MISSING,
                status_code=status.HTTP_409_CONFLICT,
            ) from exc
        except services.IdempotencyConflict as exc:
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
