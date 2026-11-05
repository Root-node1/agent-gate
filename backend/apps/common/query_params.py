"""Strict query-string parsing shared by dashboard list endpoints."""

from datetime import date, datetime, time
from datetime import timezone as datetime_timezone
from uuid import UUID

from django.utils import timezone

from .errors import ApiError, ErrorCode


def uuid_param(request, name: str) -> UUID | None:
    """Return a UUID query parameter, or reject malformed input."""
    value = request.query_params.get(name)
    if not value:
        return None
    try:
        return UUID(value)
    except ValueError as exc:
        raise ApiError(
            f"{name} must be a UUID.",
            code=ErrorCode.VALIDATION_ERROR,
            details={name: ["Enter a valid UUID."]},
        ) from exc


def datetime_param(request, name: str, *, end_of_day: bool = False) -> datetime | None:
    """Return an aware datetime; a date-only value covers the whole UTC day."""
    value = request.query_params.get(name)
    if not value:
        return None
    parsed_date = None
    if len(value) == 10:
        try:
            parsed_date = date.fromisoformat(value)
        except ValueError:
            parsed_date = None
    if parsed_date is not None:
        boundary = time.max if end_of_day else time.min
        parsed = datetime.combine(parsed_date, boundary)
    else:
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ApiError(
                f"{name} must be an ISO-8601 date or datetime.",
                code=ErrorCode.VALIDATION_ERROR,
                details={name: ["Enter an ISO-8601 date or datetime."]},
            ) from exc
    if timezone.is_naive(parsed):
        parsed = timezone.make_aware(parsed, datetime_timezone.utc)
    return parsed


def ordering_param(request, allowed: tuple[str, ...], default: tuple[str, ...]) -> tuple[str, ...]:
    """Validate a comma-separated ordering list against a whitelist."""
    raw = request.query_params.get("ordering")
    if raw is None:
        return default
    fields: list[str] = []
    for token in raw.split(","):
        token = token.strip()
        if not token:
            continue
        field = token[1:] if token.startswith("-") else token
        if field not in allowed:
            raise ApiError(
                "Unknown ordering field.",
                code=ErrorCode.VALIDATION_ERROR,
                details={"ordering": [f"Order by one of: {', '.join(allowed)}."]},
            )
        fields.append(token)
    return tuple(fields) or default


def choice_param(request, name: str, choices) -> str | None:
    """Return a value from a Django TextChoices/plain iterable, or reject it."""
    value = request.query_params.get(name)
    if not value:
        return None
    allowed = choices.values if hasattr(choices, "values") else tuple(choices)
    if value not in allowed:
        raise ApiError(
            f"Unknown {name}.",
            code=ErrorCode.VALIDATION_ERROR,
            details={name: [f"Select one of: {', '.join(allowed)}."]},
        )
    return value
