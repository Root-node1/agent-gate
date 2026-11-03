"""Deterministic risk scoring for evaluated decisions."""

from collections.abc import Iterable

from .decision import Reason
from .screening import ScreeningResult

MAX_RISK_SCORE = 100

REASON_RISK_WEIGHTS: dict[str, int] = {
    "R01_AGENT_ACTIVE": 80,
    "R02_CURRENCY": 50,
    "R03_MERCHANT_BLOCK": 90,
    "R04_MERCHANT_ALLOW": 50,
    "R05_PER_TX_CAP": 40,
    "R06_DAILY_BUDGET": 50,
    "R07_MONTHLY_BUDGET": 55,
    "R08_VELOCITY": 20,
    "R09_MERCHANT_WINDOW": 25,
    "R10_APPROVAL_THRESHOLD": 15,
    "R11_NEW_PAYEE": 30,
    "R12_PAYEE_CHANGE": 70,
    "R13_UNTRUSTED_SOURCE": 25,
    "R14_INJECTION_PATTERN": 100,
    "R15_INJECTION_CLASSIFIER": 30,
    "R16_WEEKLY_BUDGET": 55,
    "engine_error": 100,
}


def score_reasons(
    reasons: Iterable[Reason], screening: ScreeningResult | None = None
) -> int:
    """Return a capped 0-100 risk score for every reason that fired."""
    score = sum(REASON_RISK_WEIGHTS.get(reason.code, 0) for reason in reasons)
    if (
        screening is not None
        and screening.classifier is not None
        and screening.classifier.available
    ):
        score += screening.classifier.score or 0
    return max(0, min(MAX_RISK_SCORE, score))
