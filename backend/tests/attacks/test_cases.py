from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import yaml
from rest_framework.test import APITestCase

from apps.accounts.models import Organization
from apps.agents.models import Agent
from apps.common.currency import normalize_currency
from apps.common.money import to_minor
from apps.policies.models import MerchantRule, Policy
from apps.spend.models import SpendRequest

URL = "/v1/spend-requests/"
CASES = yaml.safe_load((Path(__file__).parent / "cases.yaml").read_text())["cases"]


class AttackCorpusTests(APITestCase):
    def setUp(self):
        self.organization = Organization.objects.create(name="corpus")

    def build_policy(self, agent, overrides):
        values = {
            "currency": normalize_currency(overrides.get("currency", "USD")),
            "per_transaction_cap_minor": to_minor(
                Decimal(overrides.get("per_transaction_cap", "100.00")), "USD"
            ),
            "approval_threshold_minor": to_minor(
                Decimal(overrides.get("approval_threshold", "50.00")), "USD"
            ),
            "daily_budget_minor": to_minor(Decimal(overrides.get("daily_budget", "500.00")), "USD"),
            "weekly_budget_minor": to_minor(
                Decimal(overrides.get("weekly_budget", "5000.00")), "USD"
            ),
            "monthly_budget_minor": to_minor(
                Decimal(overrides.get("monthly_budget", "5000.00")), "USD"
            ),
            "merchant_mode": overrides.get("merchant_mode", Policy.MerchantMode.BLOCKLIST),
            "untrusted_source_action": overrides.get(
                "untrusted_source_action", Policy.UntrustedSourceAction.NEEDS_APPROVAL
            ),
            "velocity_max_count": int(overrides.get("velocity_max_count", 0)),
            "velocity_window_seconds": int(overrides.get("velocity_window_seconds", 3_600)),
            "merchant_window_cap_minor": to_minor(
                Decimal(overrides.get("merchant_window_cap", "0")), "USD"
            ),
        }
        return Policy.objects.create(agent=agent, **values)

    def run_case(self, case):
        agent, key = Agent.create_with_key(case["id"], self.organization)
        policy = self.build_policy(agent, case.get("policy", {}))
        for rule in case.get("rules", []):
            values = dict(rule)
            values["merchant_ref"] = values.pop("merchant")
            MerchantRule.objects.create(policy=policy, **values)
        for amount in case.get("prior_approved_spend", []):
            SpendRequest.objects.create(
                organization=self.organization,
                agent=agent,
                policy=policy,
                policy_version=policy.version,
                amount_minor=to_minor(Decimal(amount), policy.currency),
                currency=policy.currency,
                merchant_ref="acme.com",
                decision=SpendRequest.Decision.ALLOW,
                status=SpendRequest.Status.APPROVED,
            )

        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {key}")
        request = dict(case["request"])
        request.setdefault("currency", policy.currency)
        response = self.client.post(
            URL, request, format="json", HTTP_IDEMPOTENCY_KEY=str(uuid4())
        )
        self.assertEqual(response.status_code, 201, response.content)
        body = response.json()
        expect = case["expect"]
        self.assertEqual(body["decision"], expect["decision"], case["description"])
        for rule in expect.get("rules_all", []):
            self.assertIn(rule, body["matched_rules"])
        for rule in expect.get("rules_any", []):
            self.assertIn(rule, body["matched_rules"])
        return body

    def test_enforced_cases(self):
        for case in CASES:
            if case.get("known_gap"):
                continue
            with self.subTest(case=case["id"]):
                self.run_case(case)

    def test_documented_known_gaps_match_current_behavior(self):
        known_gaps = [case for case in CASES if case.get("known_gap")]
        self.assertTrue(known_gaps)
        for case in known_gaps:
            with self.subTest(case=case["id"]):
                self.assertTrue(case["known_gap"].strip())
                self.run_case(case)
