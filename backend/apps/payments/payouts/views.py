"""DRF views for durable payout reservation and submission (INT-13I / INT-13J).

Authentication: DashboardSessionAuthentication (human admin sessions only;
machine-agent API keys are intentionally rejected for financial-initiation
endpoints).

Permissions: IsOrganizationAdmin (admin role + MFA enforced upstream).

Endpoints:
- ``POST /v1/payout-reservations/`` — durably reserve a payout for an
  approved SpendRequest.  Reservation does NOT transfer money and makes NO
  PayPal API call.
- ``POST /v1/payout-reservations/<uuid:pk>/submit/`` — submit an existing
  reservation to PayPal Payouts v1 sandbox.
- ``GET /v1/payout-reservations/<uuid:pk>/reconcile/`` — reconcile a pending
  or uncertain submission with PayPal batch/item status.
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
from apps.common.errors import ApiError, ErrorCode

from . import services
from .models import PayoutReservation
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
            raise ApiError(
                "Payouts is not configured.",
                code=ErrorCode.SERVICE_UNAVAILABLE,
                status_code=503,
            )

        # --- Organization scoping (admin-only; 404 hides existence) -----
        organization = get_object_or_404(
            Organization.objects.filter(
                memberships__user=request.user,
                memberships__role=OrgMembership.Role.ADMIN,
            ),
        )

        try:
            reservation, replayed = services.reserve_payout(
                organization,
                spend_request_id=validated["spend_request"],
                idempotency_key=validated["idempotency_key"],
                django_settings=settings,
            )
        except services.PayoutFeatureDisabled:
            raise ApiError(
                "Payouts is not configured.",
                code=ErrorCode.SERVICE_UNAVAILABLE,
                status_code=503,
            )
        except services.PayoutNotEligible as exc:
            raise ApiError(str(exc), code=ErrorCode.RECHECK_FAILED, status_code=422)
        except services.PayoutAlreadyReserved as exc:
            raise ApiError(str(exc), code=ErrorCode.IDEMPOTENCY_CONFLICT, status_code=409)

        response = Response(
            PayoutReservationSerializer(reservation).data,
            status=status.HTTP_200_OK if replayed else status.HTTP_201_CREATED,
        )
        if replayed:
            response["Idempotent-Replayed"] = "true"
        return response


class PayoutReservationSubmitView(APIView):
    """Submit an existing PayoutReservation to PayPal Payouts v1 sandbox."""

    authentication_classes = [DashboardSessionAuthentication]
    permission_classes = [IsOrganizationAdmin]

    @extend_schema(
        request=None,
        responses={
            201: PayoutReservationSerializer,
            200: PayoutReservationSerializer,
        },
        summary="Submit a reserved payout to PayPal Payouts sandbox",
    )
    def post(self, request, pk):
        try:
            services._require_payouts_enabled(settings)
        except services.PayoutFeatureDisabled:
            raise ApiError(
                "Payouts is not configured.",
                code=ErrorCode.SERVICE_UNAVAILABLE,
                status_code=503,
            )

        # --- Organization scoping (admin-only; 404 hides existence) -----
        organization = get_object_or_404(
            Organization.objects.filter(
                memberships__user=request.user,
                memberships__role=OrgMembership.Role.ADMIN,
            ),
        )

        reservation = get_object_or_404(
            PayoutReservation.objects.filter(organization=organization),
            pk=pk,
        )

        try:
            result = services.submit_payout(reservation.pk, django_settings=settings)
        except services.PayoutFeatureDisabled:
            raise ApiError(
                "Payouts is not configured.",
                code=ErrorCode.SERVICE_UNAVAILABLE,
                status_code=503,
            )
        except services.PayoutNotReserved as exc:
            raise ApiError(str(exc), code=ErrorCode.RECHECK_FAILED, status_code=422)

        http_status = (
            status.HTTP_201_CREATED
            if result.outcome == "submitted"
            else status.HTTP_200_OK
        )
        return Response(
            PayoutReservationSerializer(result.reservation).data,
            status=http_status,
        )


class PayoutReservationReconcileView(APIView):
    """Reconcile a pending or uncertain payout submission with PayPal."""

    authentication_classes = [DashboardSessionAuthentication]
    permission_classes = [IsOrganizationAdmin]

    @extend_schema(
        responses={200: PayoutReservationSerializer},
        summary="Reconcile a pending payout submission with PayPal",
    )
    def get(self, request, pk):
        try:
            services._require_payouts_enabled(settings)
        except services.PayoutFeatureDisabled:
            raise ApiError(
                "Payouts is not configured.",
                code=ErrorCode.SERVICE_UNAVAILABLE,
                status_code=503,
            )

        organization = get_object_or_404(
            Organization.objects.filter(
                memberships__user=request.user,
                memberships__role=OrgMembership.Role.ADMIN,
            ),
        )

        reservation = get_object_or_404(
            PayoutReservation.objects.filter(organization=organization),
            pk=pk,
        )

        result = services.reconcile_payout(reservation.pk, django_settings=settings)
        return Response(
            PayoutReservationSerializer(result.reservation).data,
            status=status.HTTP_200_OK,
        )
