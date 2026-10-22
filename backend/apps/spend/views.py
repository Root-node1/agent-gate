from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle
from rest_framework.views import APIView

from apps.agents.authentication import AgentKeyAuthentication
from apps.agents.throttling import AgentKeyRateThrottle

from . import services
from .idempotency import key_is_valid
from .models import SpendRequest
from .serializers import SpendRequestCreateSerializer, SpendRequestSerializer


class SpendRequestCreateView(APIView):
    authentication_classes = [AgentKeyAuthentication]
    throttle_classes = [AgentKeyRateThrottle, AnonRateThrottle]

    @extend_schema(
        request=SpendRequestCreateSerializer,
        responses={201: SpendRequestSerializer},
        summary="Submit a spend request",
        description=(
            "Returns 201 with the firewall's decision in the body: allow, deny or needs_approval. "
            "Always read `decision`; the status code alone does not mean the payment is allowed."
        ),
    )
    def post(self, request):
        idempotency_key = request.headers.get("Idempotency-Key", "").strip()
        if not key_is_valid(idempotency_key):
            return Response(
                {"detail": "A valid Idempotency-Key header (1-255 printable characters) is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = SpendRequestCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            spend_request, replayed = services.submit_spend_request(
                request.user.agent,
                idempotency_key=idempotency_key,
                **serializer.validated_data,
            )
        except services.PolicyMissing:
            return Response(
                {"detail": "This agent has no policy configured."},
                status=status.HTTP_409_CONFLICT,
            )
        except services.IdempotencyConflict:
            return Response(
                {"detail": "Idempotency-Key was reused with a different request."},
                status=status.HTTP_409_CONFLICT,
            )
        response = Response(
            SpendRequestSerializer(spend_request).data, status=status.HTTP_201_CREATED
        )
        if replayed:
            response["Idempotent-Replayed"] = "true"
        return response


class SpendRequestDetailView(APIView):
    authentication_classes = [AgentKeyAuthentication]
    throttle_classes = [AgentKeyRateThrottle, AnonRateThrottle]

    @extend_schema(responses={200: SpendRequestSerializer}, summary="Get a spend request")
    def get(self, request, pk):
        spend_request = get_object_or_404(
            SpendRequest.objects.select_related("approval"),
            pk=pk,
            agent=request.user.agent,
        )
        return Response(SpendRequestSerializer(spend_request).data)
