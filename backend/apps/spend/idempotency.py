"""Stable fingerprints for replay-safe spend requests."""

import hashlib
import json

MAX_KEY_LENGTH = 255


def key_is_valid(value: str) -> bool:
    """An idempotency key is a short, printable token chosen by the client."""
    return bool(value) and len(value) <= MAX_KEY_LENGTH and not any(
        ord(char) < 32 or ord(char) == 127 for char in value
    )


def request_hash(
    *,
    amount_minor: int,
    currency: str,
    merchant_ref: str,
    purpose: str,
    source_type: str,
    source_ref: str,
    evidence_excerpt: str,
    destination_type: str,
    destination_value: str,
) -> str:
    """Hash every field that changes what is being paid, including the destination."""
    payload = {
        "amount_minor": amount_minor,
        "currency": currency,
        "merchant_ref": merchant_ref,
        "purpose": purpose,
        "source_type": source_type,
        "source_ref": source_ref,
        "evidence_excerpt": evidence_excerpt,
        "destination_type": destination_type,
        "destination_value": destination_value,
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(encoded.encode()).hexdigest()
