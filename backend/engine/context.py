"""Immutable inputs and limits for one policy evaluation."""

from dataclasses import dataclass, field
from decimal import Decimal


@dataclass(frozen=True)
class PolicyLimits:
    """The numeric limits and merchant lists that apply to a request."""

    currency: str
    per_transaction_cap: Decimal
    approval_threshold: Decimal
    daily_budget: Decimal
    monthly_budget: Decimal
    weekly_budget: Decimal | None = None
    allowed_merchants: frozenset[str] = frozenset()
    blocked_merchants: frozenset[str] = frozenset()
    untrusted_source_action: str = "needs_approval"
    velocity_max_count: int = 0
    merchant_window_cap: Decimal = Decimal("0")


@dataclass(frozen=True)
class SpendInput:
    """One normalized spend request. Nothing here needs further validation."""

    amount: Decimal
    currency: str
    merchant: str
    source: str
    purpose: str = ""
    evidence_excerpt: str = ""
    agent_active: bool = True


@dataclass(frozen=True)
class Spent:
    """Prior usage counted against the same policy currency and merchant."""

    today: Decimal
    this_month: Decimal
    this_week: Decimal = Decimal("0")
    velocity_count: int = 0
    merchant_window_spend: Decimal = Decimal("0")


@dataclass(frozen=True)
class EvaluationContext:
    """Everything a rule needs, with no database or clock access."""

    spend: SpendInput
    limits: PolicyLimits
    spent: Spent = field(default_factory=lambda: Spent(Decimal("0"), Decimal("0")))
