from decimal import Decimal

from rest_framework.test import APITestCase

from .models import Agent, Approval, AuditEvent, MerchantRule, Policy

URL = "/v1/spend-requests/"


class ApiTestBase(APITestCase):
    def setUp(self):
        self.agent, self.key = Agent.create_with_key("shopper")
        self.policy = Policy.objects.create(agent=self.agent)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {self.key}")

    def post(self, **overrides):
        body = {"amount": "10.00", "currency": "USD", "merchant": "acme.com", "source": "trusted"}
        body.update(overrides)
        return self.client.post(URL, body, format="json")


class AuthTests(ApiTestBase):
    def test_missing_key_is_rejected(self):
        self.client.credentials()
        self.assertEqual(self.post().status_code, 401)

    def test_wrong_key_is_rejected(self):
        self.client.credentials(HTTP_AUTHORIZATION="Bearer agk_not-a-real-key")
        self.assertEqual(self.post().status_code, 401)

    def test_suspended_agent_is_rejected(self):
        self.agent.status = Agent.Status.SUSPENDED
        self.agent.save()
        self.assertEqual(self.post().status_code, 401)


class DecisionTests(ApiTestBase):
    def test_small_trusted_request_is_allowed_and_audited(self):
        response = self.post()
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["decision"], "allow")
        self.assertFalse(Approval.objects.exists())
        events = set(AuditEvent.objects.values_list("event_type", flat=True))
        self.assertEqual(events, {"spend_request.received", "spend_request.decided"})

    def test_over_threshold_creates_pending_approval(self):
        response = self.post(amount="75.00")
        self.assertEqual(response.json()["decision"], "needs_approval")
        self.assertEqual(response.json()["approval"], "pending")
        self.assertTrue(AuditEvent.objects.filter(event_type="approval.requested").exists())

    def test_blocked_merchant_is_denied_even_as_url(self):
        MerchantRule.objects.create(policy=self.policy, merchant="evil.com", action="block")
        response = self.post(merchant="https://www.evil.com/pay")
        self.assertEqual(response.json()["decision"], "deny")
        self.assertIn("MERCHANT_BLOCKED", response.json()["matched_rules"])

    def test_injected_payment_to_unknown_merchant_is_denied(self):
        MerchantRule.objects.create(policy=self.policy, merchant="acme.com", action="allow")
        response = self.post(merchant="pay-now.example", source="untrusted")
        body = response.json()
        self.assertEqual(body["decision"], "deny")
        self.assertIn("MERCHANT_NOT_ALLOWED", body["matched_rules"])
        self.assertIn("UNTRUSTED_SOURCE", body["matched_rules"])

    def test_missing_source_fails_closed(self):
        response = self.client.post(
            URL, {"amount": "10.00", "currency": "USD", "merchant": "acme.com"}, format="json"
        )
        self.assertEqual(response.json()["decision"], "needs_approval")
        self.assertIn("UNKNOWN_SOURCE", response.json()["matched_rules"])

    def test_daily_budget_accumulates(self):
        self.policy.daily_budget = Decimal("25.00")
        self.policy.save()
        self.assertEqual(self.post().json()["decision"], "allow")
        self.assertEqual(self.post().json()["decision"], "allow")
        third = self.post().json()
        self.assertEqual(third["decision"], "deny")
        self.assertIn("OVER_DAILY_BUDGET", third["matched_rules"])

    def test_denied_requests_do_not_count_toward_budget(self):
        self.policy.daily_budget = Decimal("25.00")
        self.policy.save()
        self.assertEqual(self.post(amount="30.00").json()["decision"], "deny")
        self.assertEqual(self.post(amount="20.00").json()["decision"], "allow")

    def test_invalid_payload_is_rejected(self):
        self.assertEqual(self.post(amount="-5").status_code, 400)

    def test_agent_without_policy_gets_conflict(self):
        self.policy.delete()
        self.assertEqual(self.post().status_code, 409)


class DetailTests(ApiTestBase):
    def test_agent_can_read_its_own_request(self):
        created = self.post().json()
        response = self.client.get(f"{URL}{created['id']}/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["id"], created["id"])

    def test_agent_cannot_read_another_agents_request(self):
        created = self.post().json()
        _, other_key = Agent.create_with_key("other")
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {other_key}")
        self.assertEqual(self.client.get(f"{URL}{created['id']}/").status_code, 404)


class SchemaTests(APITestCase):
    def test_openapi_schema_is_served(self):
        self.assertEqual(self.client.get("/api/schema/").status_code, 200)
