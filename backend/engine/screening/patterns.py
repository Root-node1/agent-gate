"""Deterministic phrase backstop for text that tries to override the payment policy.

This is not an injection classifier. It normalizes common Unicode evasions and denies
known override phrases; paraphrases can still get through.
"""

import re
import unicodedata

CONFUSABLES = str.maketrans(
    {
        "\u0430": "a",
        "\u0435": "e",
        "\u043e": "o",
        "\u0440": "p",
        "\u0441": "c",
        "\u0443": "y",
        "\u0445": "x",
        "\u0456": "i",
        "\u0458": "j",
        "\u0455": "s",
        "\u0501": "d",
        "\u04bb": "h",
        "\u04cf": "l",
        "\u03b1": "a",
        "\u03b5": "e",
        "\u03bf": "o",
        "\u03c1": "p",
        "\u03c4": "t",
        "\u03c5": "u",
        "\u03c7": "x",
        "\u03b9": "i",
        "\u03ba": "k",
        "\u03bd": "v",
    }
)

INJECTION_PATTERNS = tuple(
    re.compile(pattern)
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


def normalize_text(value: str) -> str:
    """Canonicalize text before phrase matching without changing its meaning."""
    text = unicodedata.normalize("NFKC", value)
    text = "".join(char for char in text if unicodedata.category(char) != "Cf")
    text = text.casefold().translate(CONFUSABLES)
    return " ".join(text.split())


def contains_injection(*texts: str) -> bool:
    """Return True when any supplied field contains a known override phrase."""
    return any(
        pattern.search(normalize_text(text))
        for text in texts
        for pattern in INJECTION_PATTERNS
    )
