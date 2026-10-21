"""Agent API key generation, hashing, and constant-time lookup."""

import hashlib
import hmac
import secrets

KEY_PREFIX = "agk_"
PREFIX_LENGTH = 12


def hash_key(raw_key: str) -> str:
    """Return the SHA-256 hex digest stored for an agent key."""
    return hashlib.sha256(raw_key.encode()).hexdigest()


def key_prefix(raw_key: str) -> str:
    """Return the indexed, non-secret prefix of a raw agent key."""
    return raw_key[:PREFIX_LENGTH]


def new_raw_key() -> str:
    """Generate a new raw agent key. Only this value is ever shown to a caller."""
    return KEY_PREFIX + secrets.token_urlsafe(32)


def hash_matches(raw_key: str, stored_hash: str) -> bool:
    """Compare a presented key with a stored hash without leaking timing."""
    return hmac.compare_digest(hash_key(raw_key), stored_hash)
