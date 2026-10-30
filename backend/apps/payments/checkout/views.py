"""DRF views for PayPal sandbox checkout order creation (INT-13G).

Authentication: DashboardSessionAuthentication (human admin sessions only;
machine-agent API keys are intentionally rejected for financial-initiation
endpoints).

Permissions: IsOrganizationAdmin (admin role + MFA enforced upstream).

The endpoint is deliberately minimal: ``POST /v1/checkout-orders/``.
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
from apps.common.money import to_minor
from apps.payments.paypal.client import PayPalAPIError, PayPalClient
from apps.payments.paypal.config import PayPalConfigError, get_paypal_config

from . import services
from .serializers import CheckoutOrderCreateSerializer, CheckoutOrderSerializer


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
            return Response(
                {"detail": "PayPal is not configured."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        if not config.checkout_enabled:
            return Response(
                {"detail": "Checkout is not enabled."},
                status=status.HTTP_403_FORBIDDEN,
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
            return Response(
                {"detail": "Idempotency-Key was reused with a different request."},
                status=status.HTTP_409_CONFLICT,
            )
        except PayPalAPIError as exc:
            # PayPal rejected the request; the order is already marked DECLINED.
            return Response(
                {"detail": str(exc)},
                status=status.HTTP_502_BAD_GATEWAY,
            )

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
