"""Canonical JSON and hash construction for the append-only audit chain."""

import hashlib
import json
from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import UUID

GENESIS_HASH = "0" * 64
CHAIN_VERSION = 1


def _canonical_value(value):
    if isinstance(value, float):
        raise ValueError("Audit payload values must not be floats.")
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).isoformat(timespec="microseconds")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): _canonical_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_canonical_value(item) for item in value]
    return value


def canonical_payload(payload):
    """Return a JSONB-safe value with stable types and no floating point numbers."""
    encoded = json.dumps(
        _canonical_value(payload),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )
    return json.loads(encoded)


def event_hash(
    *,
    prev_hash: str,
    created_at: datetime,
    event_type: str,
    actor_type: str,
    actor_id: str,
    organization_id,
    agent_id,
    spend_request_id,
    payload,
) -> str:
    """Hash the canonical envelope that will be stored beside the event."""
    envelope = {
        "version": CHAIN_VERSION,
        "prev_hash": prev_hash,
        "created_at": created_at.astimezone(timezone.utc).isoformat(timespec="microseconds"),
        "event_type": event_type,
        "actor_type": actor_type,
        "actor_id": actor_id,
        "organization_id": str(organization_id),
        "agent_id": str(agent_id) if agent_id else None,
        "spend_request_id": str(spend_request_id) if spend_request_id else None,
        "payload": canonical_payload(payload),
    }
    encoded = json.dumps(envelope, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(encoded.encode()).hexdigest()
