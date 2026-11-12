"""DRF views for PayPal sandbox checkout order creation and capture (INT-13G, INT-13H).

Authentication: DashboardSessionAuthentication (human admin sessions only;
machine-agent API keys are intentionally rejected for financial-initiation
endpoints).

Permissions: IsOrganizationAdmin (admin role + MFA enforced upstream).

Endpoints:
- ``POST /v1/checkout-orders/`` — create a checkout order (CAPTURE intent).
- ``POST /v1/checkout-orders/{id}/capture/`` — explicitly capture an approved
  order.  Approval is never inferred from a redirect or browser parameter.
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
from apps.common.money import to_minor
from apps.payments.models import CheckoutOrder
from apps.payments.paypal.client import PayPalAPIError, PayPalClient
from apps.payments.paypal.config import PayPalConfigError, get_paypal_config

from . import services
from .serializers import (
    CheckoutOrderCaptureSerializer,
    CheckoutOrderCreateSerializer,
    CheckoutOrderSerializer,
)


class CheckoutOrderCreateView(APIView):
    """Create a PayPal Sandbox checkout order (CAPTURE intent)."""

    authentication_classes = [DashboardSessionAuthentication]
    permission_classes = [IsOrganizationAdmin]

    @extend_schema(
        request=CheckoutOrderCreateSerializer,
        responses={
            201: CheckoutOrderSerializer,
            200: CheckoutOrderSerializer,
            202: CheckoutOrderSerializer,
        },
        summary="Create a PayPal sandbox checkout order",
    )
    def post(self, request):
        serializer = CheckoutOrderCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        validated = serializer.validated_data

        # --- Feature gate + credential check ----------------------------------
        try:
            config = get_paypal_config(settings)
        except PayPalConfigError:
            raise ApiError(
                "PayPal is not configured.",
                code=ErrorCode.SERVICE_UNAVAILABLE,
                status_code=503,
            )

        if not config.checkout_enabled:
            raise ApiError(
                "Checkout is not enabled.",
                code=ErrorCode.PERMISSION_DENIED,
                status_code=403,
            )

        # --- Organization scoping (admin-only; 404 hides existence) ----------
        organization = get_object_or_404(
            Organization.objects.filter(
                memberships__user=request.user,
                memberships__role=OrgMembership.Role.ADMIN,
            ),
            pk=validated["organization"],
        )

        # --- Build client from validated config -------------------------------
        client = PayPalClient(config.client_id, config.client_secret)

        # --- Delegate to the service layer ------------------------------------
        amount_minor = to_minor(validated["amount"], validated["currency"])
        try:
            checkout, approval_url, replayed = services.create_checkout_order(
                organization,
                amount_minor=amount_minor,
                currency=validated["currency"],
                idempotency_key=validated["idempotency_key"],
                client=client,
            )
        except services.CheckoutOperationConflict:
            raise ApiError(
                "Idempotency-Key was reused with a different request.",
                code=ErrorCode.IDEMPOTENCY_CONFLICT,
                status_code=409,
            )
        except PayPalAPIError as exc:
            # PayPal rejected the request; the order is already marked DECLINED.
            raise ApiError(str(exc), code=ErrorCode.SERVICE_UNAVAILABLE, status_code=502)

        # --- Response ---------------------------------------------------------
        response = Response(
            CheckoutOrderSerializer(checkout).data,
            status=status.HTTP_200_OK
            if replayed
            else (
                status.HTTP_201_CREATED
                if approval_url is not None
                else status.HTTP_202_ACCEPTED
            ),
        )
        if replayed:
            response["Idempotent-Replayed"] = "true"
        return response


class CheckoutOrderCaptureView(APIView):
    """Explicitly capture a previously-approved PayPal checkout order.

    The payer returning from PayPal is *not* proof of approval or payment;
    approval is verified server-side via ``GET /v2/checkout/orders/{id}``
    before the capture is submitted.  The endpoint is admin-only and returns
    safe, normalized responses for every terminal and recoverable outcome.
    """

    authentication_classes = [DashboardSessionAuthentication]
    permission_classes = [IsOrganizationAdmin]

    @extend_schema(
        request=CheckoutOrderCaptureSerializer,
        responses={
            200: CheckoutOrderSerializer,
            202: CheckoutOrderSerializer,
            409: CheckoutOrderSerializer,
            422: CheckoutOrderSerializer,
            502: CheckoutOrderSerializer,
            503: CheckoutOrderSerializer,
        },
        summary="Capture an approved PayPal sandbox checkout order",
    )
    def post(self, request, pk):
        serializer = CheckoutOrderCaptureSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        capture_key = serializer.validated_data["capture_idempotency_key"]

        # --- Feature gate + credential check ----------------------------------
        try:
            config = get_paypal_config(settings)
        except PayPalConfigError:
            raise ApiError(
                "PayPal is not configured.",
                code=ErrorCode.SERVICE_UNAVAILABLE,
                status_code=503,
            )
        if not config.checkout_enabled:
            raise ApiError(
                "Checkout is not enabled.",
                code=ErrorCode.PERMISSION_DENIED,
                status_code=403,
            )

        # --- Organization scoping (admin-only; 404 hides existence) ----------
        checkout = get_object_or_404(
            CheckoutOrder.objects.filter(
                organization__in=Organization.objects.filter(
                    memberships__user=request.user,
                    memberships__role=OrgMembership.Role.ADMIN,
                ),
            ),
            pk=pk,
        )

        client = PayPalClient(config.client_id, config.client_secret)

        # --- Delegate to the service layer ------------------------------------
        try:
            checkout, outcome, replayed = services.capture_checkout_order(
                checkout_order=checkout,
                organization_id=checkout.organization_id,
                capture_idempotency_key=capture_key,
                client=client,
            )
        except services.CaptureConflict:
            raise ApiError(
                "A capture operation is already in progress for this order.",
                code=ErrorCode.APPROVAL_CONFLICT,
                status_code=409,
            )
        except services.CaptureNotApproved as exc:
            raise ApiError(str(exc), code=ErrorCode.APPROVAL_CONFLICT, status_code=409)
        except services.CaptureVerificationError as exc:
            raise ApiError(str(exc), code=ErrorCode.RECHECK_FAILED, status_code=422)
        except PayPalAPIError as exc:
            # PayPal rejected the attempt; the order is already marked DECLINED.
            raise ApiError(str(exc), code=ErrorCode.SERVICE_UNAVAILABLE, status_code=502)

        # --- Response --------------------------------------------------------
        response = Response(
            CheckoutOrderSerializer(checkout).data,
            status=(
                status.HTTP_200_OK
                if outcome == services.CaptureOutcome.COMPLETED
                else status.HTTP_202_ACCEPTED
            ),
        )
        if outcome == services.CaptureOutcome.COMPLETED and replayed:
            response["Idempotent-Replayed"] = "true"
        return response
