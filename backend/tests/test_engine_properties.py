from decimal import Decimal

from django.test import SimpleTestCase
from hypothesis import given, settings
from hypothesis import strategies as st

from engine import (
    ALLOW,
    DENY,
    MAX_RISK_SCORE,
    SOURCE_TRUSTED,
    SOURCE_UNKNOWN,
    SOURCE_UNTRUSTED,
    ClassifierResult,
    EvaluationContext,
    PayeeState,
    PolicyLimits,
    Reason,
    ScreeningResult,
    SpendInput,
    Spent,
    evaluate_context,
    score_reasons,
)
from engine.scoring import REASON_RISK_WEIGHTS

MONEY = st.decimals(min_value=Decimal("0"), max_value=Decimal("100000"), places=2)
SOURCES = st.sampled_from([SOURCE_TRUSTED, SOURCE_UNTRUSTED, SOURCE_UNKNOWN])
CLASSIFIER_SCORES = st.integers(min_value=0, max_value=100)


def context(
    *,
    amount=Decimal("10"),
    limits=None,
    spent=None,
    screening=None,
    payee=None,
    source=SOURCE_TRUSTED,
):
    return EvaluationContext(
        spend=SpendInput(
            amount=amount,
            currency="USD",
            merchant="acme.com",
            source=source,
        ),
        limits=limits
        or PolicyLimits(
            currency="USD",
            per_transaction_cap=Decimal("100"),
            approval_threshold=Decimal("50"),
            daily_budget=Decimal("500"),
            monthly_budget=Decimal("5000"),
        ),
        spent=spent or Spent(today=Decimal("0"), this_month=Decimal("0")),
        screening=screening,
        payee=payee,
    )


class RiskScoreProperties(SimpleTestCase):
    @settings(max_examples=60, deadline=None)
    @given(
        amount=MONEY,
        cap=MONEY,
        threshold=MONEY,
        daily=MONEY,
        monthly=MONEY,
        source=SOURCES,
        classifier_score=CLASSIFIER_SCORES,
    )
    def test_risk_score_always_stays_in_range(
        self,
        amount,
        cap,
        threshold,
        daily,
        monthly,
        source,
        classifier_score,
    ):
        limits = PolicyLimits(
            currency="USD",
            per_transaction_cap=cap,
            approval_threshold=threshold,
            daily_budget=daily,
            monthly_budget=monthly,
        )
        decision = evaluate_context(
            context(
                amount=amount,
                limits=limits,
                screening=ScreeningResult(
                    classifier=ClassifierResult(score=classifier_score)
                ),
                source=source,
            )
        )
        self.assertGreaterEqual(decision.risk_score, 0)
        self.assertLessEqual(decision.risk_score, MAX_RISK_SCORE)

    @settings(max_examples=40, deadline=None)
    @given(
        low=CLASSIFIER_SCORES,
        high=CLASSIFIER_SCORES,
        codes=st.lists(st.sampled_from(sorted(REASON_RISK_WEIGHTS)), max_size=8),
    )
    def test_higher_classifier_score_never_lowers_risk(self, low, high, codes):
        if low > high:
            low, high = high, low
        reasons = tuple(Reason(code=code, message="", outcome="") for code in codes)
        low_score = score_reasons(
            reasons,
            ScreeningResult(classifier=ClassifierResult(score=low)),
        )
        high_score = score_reasons(
            reasons,
            ScreeningResult(classifier=ClassifierResult(score=high)),
        )
        self.assertLessEqual(low_score, high_score)


class ClassifierProperties(SimpleTestCase):
    @settings(max_examples=60, deadline=None)
    @given(
        score=CLASSIFIER_SCORES,
        threshold=CLASSIFIER_SCORES,
        required=st.booleans(),
    )
    def test_classifier_never_denies_or_downgrades_a_deny(self, score, threshold, required):
        limits = PolicyLimits(
            currency="USD",
            per_transaction_cap=Decimal("100"),
            approval_threshold=Decimal("50"),
            daily_budget=Decimal("500"),
            monthly_budget=Decimal("5000"),
            injection_escalate_threshold=threshold,
            classifier_required=required,
        )
        allowed = evaluate_context(
            context(
                limits=limits,
                screening=ScreeningResult(classifier=ClassifierResult(score=score)),
            )
        )
        self.assertIn(allowed.outcome, (ALLOW, "needs_approval"))

        denied = evaluate_context(
            context(
                amount=Decimal("1000"),
                limits=limits,
                screening=ScreeningResult(classifier=ClassifierResult(score=score)),
            )
        )
        self.assertEqual(denied.outcome, DENY)


class PayeePrecedenceProperties(SimpleTestCase):
    @settings(max_examples=40, deadline=None)
    @given(
        known=st.booleans(),
        trusted=st.booleans(),
        within_cooldown=st.booleans(),
        destination_changed=st.booleans(),
    )
    def test_payee_state_never_overrides_a_hard_deny(
        self,
        known,
        trusted,
        within_cooldown,
        destination_changed,
    ):
        limits = PolicyLimits(
            currency="USD",
            per_transaction_cap=Decimal("100"),
            approval_threshold=Decimal("50"),
            daily_budget=Decimal("500"),
            monthly_budget=Decimal("5000"),
            blocked_merchants=frozenset({"acme.com"}),
            new_payee_cooldown_hours=24,
        )
        decision = evaluate_context(
            context(
                limits=limits,
                payee=PayeeState(
                    known=known,
                    trusted=trusted,
                    within_cooldown=within_cooldown,
                    destination_changed=destination_changed,
                ),
            )
        )
        self.assertEqual(decision.outcome, DENY)
