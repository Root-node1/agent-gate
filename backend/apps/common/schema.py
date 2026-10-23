"""OpenAPI components for the shared error envelope."""

from drf_spectacular.utils import OpenApiResponse
from rest_framework import serializers

from .errors import ErrorCode


class ErrorDetailSerializer(serializers.Serializer):
    """The machine-readable part of an API error."""

    code = serializers.ChoiceField(choices=ErrorCode.choices)
    message = serializers.CharField()
    details = serializers.DictField()


class ErrorEnvelopeSerializer(serializers.Serializer):
    """Every API failure returns this envelope plus the request id header."""

    error = ErrorDetailSerializer()
    request_id = serializers.CharField(
        help_text="Server-generated request identifier, also sent as X-Request-Id."
    )


def error_response(description: str = "Error response envelope.") -> OpenApiResponse:
    """Build one documented error response with the request id header."""
    return OpenApiResponse(
        response=ErrorEnvelopeSerializer,
        description=f"{description} The X-Request-Id header carries the same request id.",
    )


def error_responses(*status_codes: int) -> dict[int, OpenApiResponse]:
    """Map status codes to the shared error response component."""
    return {status_code: error_response() for status_code in status_codes}
