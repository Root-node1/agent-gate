"""Spend rule engine.

Pure functions: no database, no network, no model calls. Everything a rule needs
is passed in, so every decision is deterministic and easy to test.

Precedence: any deny wins; otherwise any approval reason means needs_approval;
otherwise allow. All triggered rules are reported, not just the first.
"""

from dataclasses import dataclass
from decimal import Decimal

ALLOW = "allow"
DENY = "deny"
NEEDS_APPROVAL = "needs_approval"

SOURCE_TRUSTED = "trusted"
SOURCE_UNTRUSTED = "untrusted"
SOURCE_UNKNOWN = "unknown"


def normalize_merchant(value: str) -> str:
    """Lowercase and strip scheme, path and a leading www so URLs match plain domains."""
    merchant = value.strip().lower()
    merchant = merchant.split("://")[-1]
    merchant = merchant.split("/")[0]
    if merchant.startswith("www."):
        merchant = merchant[4:]
    return merchant


@dataclass(frozen=True)
class PolicyLimits:
    currency: str
    per_transaction_cap: Decimal
    approval_threshold: Decimal
    daily_budget: Decimal
    monthly_budget: Decimal
    allowed_merchants: frozenset[str] = frozenset()
    blocked_merchants: frozenset[str] = frozenset()


@dataclass(frozen=True)
class SpendInput:
    amount: Decimal
    currency: str
    merchant: str
    source: str


@dataclass(frozen=True)
class Spent:
    """Money already counted against the budgets (same currency as the policy)."""

    today: Decimal
    this_month: Decimal


@dataclass(frozen=True)
class Reason:
    code: str
    message: str
    outcome: str  # DENY or NEEDS_APPROVAL


@dataclass(frozen=True)
class Decision:
    outcome: str
    reasons: tuple[Reason, ...]

    @property
    def matched_rules(self) -> list[str]:
        return [reason.code for reason in self.reasons]


def evaluate(spend: SpendInput, limits: PolicyLimits, spent: Spent) -> Decision:
    reasons: list[Reason] = []
    merchant = normalize_merchant(spend.merchant)
    blocked = {normalize_merchant(m) for m in limits.blocked_merchants}
    allowed = {normalize_merchant(m) for m in limits.allowed_merchants}
    currency = limits.currency

    def deny(code: str, message: str) -> None:
        reasons.append(Reason(code, message, DENY))

    def needs_approval(code: str, message: str) -> None:
        reasons.append(Reason(code, message, NEEDS_APPROVAL))

    # Hard rules: any of these denies the request.
    if spend.amount <= 0:
        deny("INVALID_AMOUNT", "Amount must be greater than zero.")
    if spend.currency.upper() != currency.upper():
        deny("CURRENCY_MISMATCH", f"Request is in {spend.currency}, policy is in {currency}.")
    if merchant in blocked:
        deny("MERCHANT_BLOCKED", f"Merchant {merchant} is on the block list.")
    if allowed and merchant not in allowed:
        deny("MERCHANT_NOT_ALLOWED", f"Merchant {merchant} is not on the allow list.")
    if spend.amount > limits.per_transaction_cap:
        deny(
            "OVER_TRANSACTION_CAP",
            f"{spend.amount} {currency} exceeds the per-transaction cap of {limits.per_transaction_cap}.",
        )
    if spent.today + spend.amount > limits.daily_budget:
        deny(
            "OVER_DAILY_BUDGET",
            f"Would bring today's spend to {spent.today + spend.amount} {currency}, "
            f"over the daily budget of {limits.daily_budget}.",
        )
    if spent.this_month + spend.amount > limits.monthly_budget:
        deny(
            "OVER_MONTHLY_BUDGET",
            f"Would bring this month's spend to {spent.this_month + spend.amount} {currency}, "
            f"over the monthly budget of {limits.monthly_budget}.",
        )

    # Approval rules: a human must decide. Fail closed on anything not trusted.
    if spend.source == SOURCE_UNTRUSTED:
        needs_approval(
            "UNTRUSTED_SOURCE",
            "The payment instruction came from untrusted content (web page, email or invoice).",
        )
    elif spend.source != SOURCE_TRUSTED:
        needs_approval("UNKNOWN_SOURCE", "The origin of the payment instruction is unknown.")
    if spend.amount > limits.approval_threshold:
        needs_approval(
            "OVER_APPROVAL_THRESHOLD",
            f"{spend.amount} {currency} is above the approval threshold of {limits.approval_threshold}.",
        )

    if any(reason.outcome == DENY for reason in reasons):
        outcome = DENY
    elif reasons:
        outcome = NEEDS_APPROVAL
    else:
        outcome = ALLOW
    return Decision(outcome=outcome, reasons=tuple(reasons))
