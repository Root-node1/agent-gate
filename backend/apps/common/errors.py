"""One error envelope for every API failure."""

from __future__ import annotations

from enum import Enum
from typing import Any
from uuid import uuid4

from django.core.exceptions import PermissionDenied as DjangoPermissionDenied
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import DatabaseError, models
from django.http import Http404, HttpResponseForbidden, JsonResponse
from rest_framework import exceptions, status
from rest_framework.response import Response


class ErrorCode(models.TextChoices):
    """Machine-readable error codes exposed by the API."""

    BAD_REQUEST = "bad_request", "Bad request"
    VALIDATION_ERROR = "validation_error", "Validation error"
    INVALID_JSON = "invalid_json", "Invalid JSON"
    REQUEST_TOO_LARGE = "request_too_large", "Request too large"
    UNSUPPORTED_MEDIA_TYPE = "unsupported_media_type", "Unsupported media type"
    IDEMPOTENCY_KEY_REQUIRED = "idempotency_key_required", "Idempotency key required"
    AUTHENTICATION_FAILED = "authentication_failed", "Authentication failed"
    PERMISSION_DENIED = "permission_denied", "Permission denied"
    AGENT_SUSPENDED = "agent_suspended", "Agent suspended"
    NOT_FOUND = "not_found", "Not found"
    METHOD_NOT_ALLOWED = "method_not_allowed", "Method not allowed"
    IDEMPOTENCY_CONFLICT = "idempotency_conflict", "Idempotency conflict"
    POLICY_MISSING = "policy_missing", "Policy missing"
    RECHECK_FAILED = "recheck_failed", "Recheck failed"
    APPROVAL_CONFLICT = "approval_conflict", "Approval conflict"
    APPROVAL_EXPIRED = "approval_expired", "Approval expired"
    AUDIT_CHAIN_BROKEN = "audit_chain_broken", "Audit chain broken"
    THROTTLED = "throttled", "Throttled"
    PRECONDITION_REQUIRED = "precondition_required", "Precondition required"
    STALE_APPROVAL = "stale_approval", "Stale approval"
    SERVICE_UNAVAILABLE = "service_unavailable", "Service unavailable"
    INTERNAL_ERROR = "internal_error", "Internal error"


def code_value(code: ErrorCode | str) -> str:
    """Return the wire value for a code, accepting enums and plain strings."""
    return code.value if isinstance(code, Enum) else str(code)


class ApiError(exceptions.APIException):
    """An API failure with a stable code, message, and structured details."""

    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = "The request could not be processed."
    default_code = ErrorCode.BAD_REQUEST

    def __init__(
        self,
        message: str | None = None,
        *,
        code: ErrorCode | str | None = None,
        status_code: int | None = None,
        details: dict[str, Any] | None = None,
    ):
        self.code = code_value(code or self.default_code)
        self.details = details or {}
        if status_code is not None:
            self.status_code = status_code
        super().__init__(message or self.default_detail, code=self.code)


class AgentSuspended(ApiError):
    """A valid key belongs to an agent that is no longer allowed to spend."""

    status_code = status.HTTP_403_FORBIDDEN
    default_detail = "The agent is suspended."
    default_code = ErrorCode.AGENT_SUSPENDED


def ensure_request_id(request) -> str:
    """Return the request id, generating one when middleware was not involved."""
    request_id = getattr(request, "request_id", None) if request is not None else None
    if not request_id:
        request_id = uuid4().hex
        if request is not None:
            request.request_id = request_id
    return request_id


def _plain(value: Any) -> Any:
    """Convert DRF/exception values into JSON-safe structures."""
    if isinstance(value, dict):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def _details(value: Any) -> dict[str, Any]:
    """Keep error details an object even when DRF reports a bare message list."""
    plain = _plain(value)
    if isinstance(plain, dict):
        return plain
    if plain in (None, "", [], {}):
        return {}
    return {"non_field_errors": plain}


def error_payload(
    request,
    *,
    code: ErrorCode | str,
    message: str,
    details: Any = None,
) -> dict[str, Any]:
    """Build the wire envelope shared by exception handling and CSRF failures."""
    return {
        "error": {
            "code": code_value(code),
            "message": message,
            "details": _details(details),
        },
        "request_id": ensure_request_id(request),
    }


def _error_response(
    request,
    *,
    status_code: int,
    code: ErrorCode | str,
    message: str,
    details: dict[str, Any] | None = None,
) -> Response:
    response = Response(
        error_payload(request, code=code, message=message, details=details),
        status=status_code,
    )
    response["X-Request-Id"] = ensure_request_id(request)
    return response


def _validation_response(request, exc: exceptions.ValidationError) -> Response:
    return _error_response(
        request,
        status_code=status.HTTP_400_BAD_REQUEST,
        code=ErrorCode.VALIDATION_ERROR,
        message="The request is invalid.",
        details=exc.detail,
    )


def api_exception_handler(exc, context) -> Response | None:
    """Turn DRF and Django exceptions into the API error envelope."""
    request = context.get("request") if context else None

    if isinstance(exc, ApiError):
        return _error_response(
            request,
            status_code=exc.status_code,
            code=exc.code,
            message=str(exc.detail),
            details=exc.details,
        )
    if isinstance(exc, Http404):
        return _error_response(
            request,
            status_code=status.HTTP_404_NOT_FOUND,
            code=ErrorCode.NOT_FOUND,
            message="Not found.",
        )
    if isinstance(exc, DjangoPermissionDenied):
        return _error_response(
            request,
            status_code=status.HTTP_403_FORBIDDEN,
            code=ErrorCode.PERMISSION_DENIED,
            message="You do not have permission to perform this action.",
        )
    if isinstance(exc, DjangoValidationError):
        return _error_response(
            request,
            status_code=status.HTTP_400_BAD_REQUEST,
            code=ErrorCode.VALIDATION_ERROR,
            message="The request is invalid.",
            details=exc.message_dict if hasattr(exc, "message_dict") else exc.messages,
        )
    if isinstance(exc, DatabaseError):
        return _error_response(
            request,
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            code=ErrorCode.SERVICE_UNAVAILABLE,
            message="The service is temporarily unavailable.",
        )
    if not isinstance(exc, exceptions.APIException):
        return None

    if isinstance(exc, exceptions.AuthenticationFailed | exceptions.NotAuthenticated):
        return _error_response(
            request,
            status_code=status.HTTP_401_UNAUTHORIZED,
            code=ErrorCode.AUTHENTICATION_FAILED,
            message="Authentication failed.",
        )
    if isinstance(exc, exceptions.PermissionDenied):
        return _error_response(
            request,
            status_code=status.HTTP_403_FORBIDDEN,
            code=ErrorCode.PERMISSION_DENIED,
            message="You do not have permission to perform this action.",
        )
    if isinstance(exc, exceptions.NotFound):
        return _error_response(
            request,
            status_code=status.HTTP_404_NOT_FOUND,
            code=ErrorCode.NOT_FOUND,
            message="Not found.",
        )
    if isinstance(exc, exceptions.MethodNotAllowed):
        return _error_response(
            request,
            status_code=status.HTTP_405_METHOD_NOT_ALLOWED,
            code=ErrorCode.METHOD_NOT_ALLOWED,
            message="Method not allowed.",
        )
    if isinstance(exc, exceptions.Throttled):
        details = {"retry_after": exc.wait} if exc.wait is not None else {}
        return _error_response(
            request,
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            code=ErrorCode.THROTTLED,
            message="Request was throttled.",
            details=details,
        )
    if isinstance(exc, exceptions.ParseError):
        return _error_response(
            request,
            status_code=status.HTTP_400_BAD_REQUEST,
            code=ErrorCode.INVALID_JSON,
            message="Malformed JSON.",
        )
    if isinstance(exc, exceptions.UnsupportedMediaType):
        return _error_response(
            request,
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            code=ErrorCode.UNSUPPORTED_MEDIA_TYPE,
            message="Unsupported media type.",
        )
    if isinstance(exc, exceptions.ValidationError):
        return _validation_response(request, exc)

    code = exc.default_code if exc.default_code in ErrorCode.values else ErrorCode.BAD_REQUEST
    message = str(exc.detail) if isinstance(exc.detail, str) else "The request could not be processed."
    return _error_response(
        request,
        status_code=exc.status_code or status.HTTP_400_BAD_REQUEST,
        code=code,
        message=message,
        details=exc.detail if not isinstance(exc.detail, str) else {},
    )


def csrf_failure(request, reason: str = "") -> JsonResponse | HttpResponseForbidden:
    """Return the JSON envelope for API CSRF failures and a plain 403 elsewhere."""
    if request.path.startswith(("/v1/", "/api/")):
        payload = error_payload(
            request,
            code=ErrorCode.PERMISSION_DENIED,
            message="CSRF verification failed.",
        )
        response = JsonResponse(payload, status=status.HTTP_403_FORBIDDEN)
        response["X-Request-Id"] = ensure_request_id(request)
        return response
    return HttpResponseForbidden("CSRF verification failed.")
