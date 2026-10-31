"""DRF views for durable payout reservation (INT-13I).

Authentication: DashboardSessionAuthentication (human admin sessions only;
machine-agent API keys are intentionally rejected for financial-initiation
endpoints).

Permissions: IsOrganizationAdmin (admin role + MFA enforced upstream).

Endpoints:
- ``POST /v1/payout-reservations/`` — durably reserve a payout for an
  approved SpendRequest.  Reservation does NOT transfer money and makes NO
  PayPal API call.
"""

from django.conf import settings
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import Organization, OrgMembership
from apps.accounts.permissions import IsOrganizationAdmin
from apps.agents.authentication import DashboardSessionAuthentication

from . import services
from .serializers import (
    PayoutReservationCreateSerializer,
    PayoutReservationSerializer,
)


class PayoutReservationCreateView(APIView):
    """Durably reserve a payout for an approved SpendRequest."""

    authentication_classes = [DashboardSessionAuthentication]
    permission_classes = [IsOrganizationAdmin]

    @extend_schema(
        request=PayoutReservationCreateSerializer,
        responses={
            201: PayoutReservationSerializer,
            200: PayoutReservationSerializer,
        },
        summary="Reserve a payout for an approved SpendRequest",
    )
    def post(self, request):
        serializer = PayoutReservationCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        validated = serializer.validated_data

        # --- Feature gate + credential check ------------------------------
        try:
            services._require_payouts_enabled(settings)
        except services.PayoutFeatureDisabled:
            return Response(
                {"detail": "Payouts is not configured."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        # --- Organization scoping (admin-only; 404 hides existence) -----
        organization = get_object_or_404(
            Organization.objects.filter(
                memberships__user=request.user,
                memberships__role=OrgMembership.Role.ADMIN,
            ),
        )

        # The SpendRequest itself is resolved inside the service layer under
        # the organization lock, so we only scope the organization here.

        try:
            reservation, replayed = services.reserve_payout(
                organization,
                spend_request_id=validated["spend_request"],
                idempotency_key=validated["idempotency_key"],
                django_settings=settings,
            )
        except services.PayoutFeatureDisabled:
            return Response(
                {"detail": "Payouts is not configured."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        except services.PayoutNotEligible as exc:
            return Response(
                {"detail": str(exc)}, status=status.HTTP_422_UNPROCESSABLE_ENTITY
            )
        except services.PayoutAlreadyReserved as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)

        response = Response(
            PayoutReservationSerializer(reservation).data,
            status=status.HTTP_200_OK if replayed else status.HTTP_201_CREATED,
        )
        if replayed:
            response["Idempotent-Replayed"] = "true"
        return response
