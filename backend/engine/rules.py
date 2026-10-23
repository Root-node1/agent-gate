"""Deterministic spend rules.

Pure functions: no database, no network, no model calls. Every rule runs; any
deny wins, otherwise any escalation yields needs_approval, otherwise allow.
Messages carry no policy numbers so a decision response never reveals budgets.
"""


from .context import EvaluationContext, PolicyLimits, SpendInput, Spent
from .decision import (
    ALLOW,
    DENY,
    NEEDS_APPROVAL,
    SOURCE_TRUSTED,
    Decision,
    Reason,
)
from .screening.patterns import contains_injection


def normalize_merchant(value: str) -> str:
    """Lowercase and strip scheme, path and a leading www so URLs match plain domains."""
    merchant = value.strip().lower()
    merchant = merchant.split("://")[-1]
    merchant = merchant.split("/")[0]
    if merchant.startswith("www."):
        merchant = merchant[4:]
    return merchant


def evaluate(spend: SpendInput, limits: PolicyLimits, spent: Spent) -> Decision:
    """Run every rule and aggregate the results without short-circuiting."""
    return evaluate_context(EvaluationContext(spend=spend, limits=limits, spent=spent))


def evaluate_context(context: EvaluationContext) -> Decision:
    """Evaluate one fully built context."""
    spend = context.spend
    limits = context.limits
    spent = context.spent
    reasons: list[Reason] = []
    merchant = normalize_merchant(spend.merchant)
    blocked = {normalize_merchant(value) for value in limits.blocked_merchants}
    allowed = {normalize_merchant(value) for value in limits.allowed_merchants}
    currency = limits.currency

    def deny(code: str, message: str) -> None:
        reasons.append(Reason(code, message, DENY))

    def needs_approval(code: str, message: str) -> None:
        reasons.append(Reason(code, message, NEEDS_APPROVAL))

    if not spend.agent_active:
        deny("R01_AGENT_ACTIVE", "The agent is not active.")
    if spend.currency.upper() != currency.upper():
        deny("R02_CURRENCY", "The request currency does not match the policy currency.")
    if merchant in blocked:
        deny("R03_MERCHANT_BLOCK", "The merchant is blocked.")
    if allowed and merchant not in allowed:
        deny("R04_MERCHANT_ALLOW", "The merchant is not on the allow list.")
    if spend.amount <= 0:
        deny("R05_PER_TX_CAP", "The amount must be greater than zero.")
    elif spend.amount > limits.per_transaction_cap:
        deny("R05_PER_TX_CAP", "The amount exceeds the per-transaction cap.")
    if spent.today + spend.amount > limits.daily_budget:
        deny("R06_DAILY_BUDGET", "The request would exceed the daily budget.")
    if spent.this_month + spend.amount > limits.monthly_budget:
        deny("R07_MONTHLY_BUDGET", "The request would exceed the monthly budget.")
    if limits.weekly_budget is not None and spent.this_week + spend.amount > limits.weekly_budget:
        deny("R16_WEEKLY_BUDGET", "The request would exceed the weekly budget.")
    if (
        limits.velocity_max_count > 0
        and spent.velocity_count >= limits.velocity_max_count
    ):
        needs_approval("R08_VELOCITY", "The recent request rate exceeds the policy limit.")
    if (
        limits.merchant_window_cap > 0
        and spent.merchant_window_spend + spend.amount > limits.merchant_window_cap
    ):
        needs_approval(
            "R09_MERCHANT_WINDOW",
            "Recent spending with this merchant exceeds the policy limit.",
        )
    if spend.amount >= limits.approval_threshold:
        needs_approval("R10_APPROVAL_THRESHOLD", "The amount requires human approval.")

    if contains_injection(spend.purpose, spend.evidence_excerpt):
        deny("R14_INJECTION_PATTERN", "The request contains instructions that try to override policy.")
    elif spend.source != SOURCE_TRUSTED:
        if limits.untrusted_source_action == DENY:
            deny("R13_UNTRUSTED_SOURCE", "The payment instruction did not come from a trusted source.")
        else:
            needs_approval(
                "R13_UNTRUSTED_SOURCE",
                "The payment instruction did not come from a trusted source.",
            )

    if any(reason.outcome == DENY for reason in reasons):
        outcome = DENY
    elif reasons:
        outcome = NEEDS_APPROVAL
    else:
        outcome = ALLOW
    return Decision(outcome=outcome, reasons=tuple(reasons))


__all__ = [
    "ALLOW",
    "DENY",
    "NEEDS_APPROVAL",
    "SOURCE_TRUSTED",
    "Decision",
    "EvaluationContext",
    "PolicyLimits",
    "Reason",
    "SpendInput",
    "Spent",
    "evaluate",
    "evaluate_context",
    "normalize_merchant",
]
