from decimal import Decimal
from unittest import TestCase

from gate.rules import (
    ALLOW,
    DENY,
    NEEDS_APPROVAL,
    PolicyLimits,
    SpendInput,
    Spent,
    evaluate,
    normalize_merchant,
)

NOTHING_SPENT = Spent(today=Decimal("0"), this_month=Decimal("0"))


def make_limits(**overrides):
    values = {
        "currency": "USD",
        "per_transaction_cap": Decimal("100"),
        "approval_threshold": Decimal("50"),
        "daily_budget": Decimal("500"),
        "monthly_budget": Decimal("5000"),
    }
    values.update(overrides)
    return PolicyLimits(**values)


def make_spend(**overrides):
    values = {
        "amount": Decimal("10"),
        "currency": "USD",
        "merchant": "acme.com",
        "source": "trusted",
    }
    values.update(overrides)
    return SpendInput(**values)


class NormalizeMerchantTests(TestCase):
    def test_strips_scheme_path_and_www(self):
        self.assertEqual(normalize_merchant("https://www.Acme.com/pay?id=1"), "acme.com")

    def test_plain_domain_unchanged(self):
        self.assertEqual(normalize_merchant("acme.com"), "acme.com")


class AllowTests(TestCase):
    def test_small_trusted_request_is_allowed(self):
        decision = evaluate(make_spend(), make_limits(), NOTHING_SPENT)
        self.assertEqual(decision.outcome, ALLOW)
        self.assertEqual(decision.reasons, ())

    def test_exactly_at_threshold_is_allowed(self):
        decision = evaluate(make_spend(amount=Decimal("50")), make_limits(), NOTHING_SPENT)
        self.assertEqual(decision.outcome, ALLOW)

    def test_exactly_at_daily_budget_is_allowed(self):
        spent = Spent(today=Decimal("470"), this_month=Decimal("470"))
        decision = evaluate(make_spend(amount=Decimal("30")), make_limits(), spent)
        self.assertEqual(decision.outcome, ALLOW)


class DenyTests(TestCase):
    def test_non_positive_amount(self):
        decision = evaluate(make_spend(amount=Decimal("0")), make_limits(), NOTHING_SPENT)
        self.assertEqual(decision.outcome, DENY)
        self.assertIn("INVALID_AMOUNT", decision.matched_rules)

    def test_currency_mismatch(self):
        decision = evaluate(make_spend(currency="EUR"), make_limits(), NOTHING_SPENT)
        self.assertEqual(decision.outcome, DENY)
        self.assertIn("CURRENCY_MISMATCH", decision.matched_rules)

    def test_blocked_merchant_even_as_url(self):
        limits = make_limits(blocked_merchants=frozenset({"evil.com"}))
        decision = evaluate(make_spend(merchant="https://www.evil.com/pay"), limits, NOTHING_SPENT)
        self.assertEqual(decision.outcome, DENY)
        self.assertIn("MERCHANT_BLOCKED", decision.matched_rules)

    def test_merchant_not_on_allow_list(self):
        limits = make_limits(allowed_merchants=frozenset({"acme.com"}))
        decision = evaluate(make_spend(merchant="other.com"), limits, NOTHING_SPENT)
        self.assertEqual(decision.outcome, DENY)
        self.assertIn("MERCHANT_NOT_ALLOWED", decision.matched_rules)

    def test_lookalike_domain_is_not_on_allow_list(self):
        limits = make_limits(allowed_merchants=frozenset({"acme.com"}))
        decision = evaluate(make_spend(merchant="acme.com.evil.net"), limits, NOTHING_SPENT)
        self.assertEqual(decision.outcome, DENY)

    def test_listed_merchant_passes_allow_list(self):
        limits = make_limits(allowed_merchants=frozenset({"acme.com"}))
        decision = evaluate(make_spend(merchant="https://acme.com/checkout"), limits, NOTHING_SPENT)
        self.assertEqual(decision.outcome, ALLOW)

    def test_over_transaction_cap(self):
        decision = evaluate(make_spend(amount=Decimal("100.01")), make_limits(), NOTHING_SPENT)
        self.assertEqual(decision.outcome, DENY)
        self.assertIn("OVER_TRANSACTION_CAP", decision.matched_rules)

    def test_over_daily_budget(self):
        spent = Spent(today=Decimal("480"), this_month=Decimal("480"))
        decision = evaluate(make_spend(amount=Decimal("30")), make_limits(), spent)
        self.assertEqual(decision.outcome, DENY)
        self.assertIn("OVER_DAILY_BUDGET", decision.matched_rules)

    def test_over_monthly_budget(self):
        spent = Spent(today=Decimal("0"), this_month=Decimal("4990"))
        decision = evaluate(make_spend(amount=Decimal("20")), make_limits(), spent)
        self.assertEqual(decision.outcome, DENY)
        self.assertIn("OVER_MONTHLY_BUDGET", decision.matched_rules)


class ApprovalTests(TestCase):
    def test_over_threshold_needs_approval(self):
        decision = evaluate(make_spend(amount=Decimal("75")), make_limits(), NOTHING_SPENT)
        self.assertEqual(decision.outcome, NEEDS_APPROVAL)
        self.assertEqual(decision.matched_rules, ["OVER_APPROVAL_THRESHOLD"])

    def test_untrusted_source_needs_approval(self):
        decision = evaluate(make_spend(source="untrusted"), make_limits(), NOTHING_SPENT)
        self.assertEqual(decision.outcome, NEEDS_APPROVAL)
        self.assertIn("UNTRUSTED_SOURCE", decision.matched_rules)

    def test_unknown_source_fails_closed(self):
        decision = evaluate(make_spend(source="unknown"), make_limits(), NOTHING_SPENT)
        self.assertEqual(decision.outcome, NEEDS_APPROVAL)
        self.assertIn("UNKNOWN_SOURCE", decision.matched_rules)


class PrecedenceTests(TestCase):
    def test_deny_beats_needs_approval_and_reports_everything(self):
        limits = make_limits(blocked_merchants=frozenset({"evil.com"}))
        spend = make_spend(merchant="evil.com", source="untrusted")
        decision = evaluate(spend, limits, NOTHING_SPENT)
        self.assertEqual(decision.outcome, DENY)
        self.assertIn("MERCHANT_BLOCKED", decision.matched_rules)
        self.assertIn("UNTRUSTED_SOURCE", decision.matched_rules)
