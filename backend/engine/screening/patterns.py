"""Deterministic phrases that try to override the payment policy."""

import re

INJECTION_PATTERNS = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"\bignore\s+(?:all\s+)?(?:the\s+)?(?:previous|prior|above)\s+instructions?\b",
        r"\bdisregard\s+(?:all\s+)?(?:the\s+)?(?:previous|prior|above)\s+instructions?\b",
        r"\bignore\s+(?:the\s+)?(?:policy|rules?|limits?)\b",
        r"\boverride\s+(?:the\s+)?(?:policy|rules?|limits?|firewall)\b",
        r"\bbypass\s+(?:the\s+)?(?:policy|rules?|limits?|firewall)\b",
        r"\byou\s+are\s+now\s+(?:an?\s+)?(?:admin|administrator|developer|system)\b",
        r"\b(?:system|developer)\s+(?:prompt|message)\b",
        r"\bapprove\s+(?:this|the)\s+(?:payment|request)\b",
        r"\bdo\s+not\s+(?:tell|inform|notify)\s+(?:the\s+)?(?:user|human|operator)\b",
    )
)


def contains_injection(*texts: str) -> bool:
    """Return True when any supplied field contains a known override phrase."""
    return any(pattern.search(text) for text in texts for pattern in INJECTION_PATTERNS)
