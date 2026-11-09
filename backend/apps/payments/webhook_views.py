"""DRF view for PayPal Sandbox webhook ingestion (INT-13K)."""

from django.conf import settings
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from .webhook_service import (
    WebhookDisabled,
    WebhookIngestionError,
    WebhookMissingEventId,
    WebhookMissingHeaders,
    WebhookPayloadError,
    WebhookPayloadTooLarge,
    WebhookStorageError,
    WebhookTransportError,
    WebhookVerificationError,
    ingest_paypal_webhook,
)


@method_decorator(csrf_exempt, name="dispatch")
class PayPalWebhookView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request):
        try:
            result = ingest_paypal_webhook(
                body=request.body,
                headers=request.headers,
                django_settings=settings,
            )
        except WebhookPayloadTooLarge:
            return Response(
                {"detail": "Payload too large."},
                status=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            )
        except (WebhookMissingHeaders, WebhookPayloadError, WebhookMissingEventId):
            return Response(
                {"detail": "Invalid request."}, status=status.HTTP_400_BAD_REQUEST
            )
        except WebhookTransportError:
            return Response(
                {"detail": "Verification unavailable."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        except WebhookVerificationError:
            return Response(
                {"detail": "Verification failed."}, status=status.HTTP_400_BAD_REQUEST
            )
        except WebhookDisabled:
            return Response(
                {"detail": "Webhooks are not configured."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        except WebhookStorageError:
            return Response(
                {"detail": "Storage failed."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        except WebhookIngestionError:
            return Response(
                {"detail": "Ingestion failed."}, status=status.HTTP_400_BAD_REQUEST
            )

        return Response({"status": result}, status=status.HTTP_200_OK)
