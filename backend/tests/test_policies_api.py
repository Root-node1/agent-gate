from rest_framework.test import APITestCase

from apps.accounts.models import Organization, OrgMembership, User
from apps.agents.models import Agent
from apps.policies.models import MerchantRule, Policy


class PolicyApiTests(APITestCase):
    def setUp(self):
        self.organization = Organization.objects.create(name="acme")
        self.agent, _ = Agent.create_with_key("shopper", self.organization)
        self.policy = Policy.objects.create(agent=self.agent, weekly_budget_minor=123_400)
        MerchantRule.objects.create(policy=self.policy, merchant_ref="acme.com", kind="allow")
        self.viewer = User.objects.create_user("viewer")
        OrgMembership.objects.create(
            user=self.viewer, organization=self.organization, role=OrgMembership.Role.VIEWER
        )

    def test_list_returns_policy_numbers_and_merchants(self):
        self.client.force_authenticate(user=self.viewer)
        body = self.client.get("/v1/policies/").json()
        self.assertEqual(body["count"], 1)
        policy = body["results"][0]
        self.assertEqual(policy["weekly_budget_minor"], 123_400)
        self.assertEqual(policy["merchant_rules"][0]["merchant_ref"], "acme.com")

    def test_invalid_agent_filter_is_rejected(self):
        self.client.force_authenticate(user=self.viewer)
        self.assertEqual(self.client.get("/v1/policies/?agent=nope").status_code, 400)

    def test_policies_are_scoped_to_memberships(self):
        other_org = Organization.objects.create(name="other")
        other_agent, _ = Agent.create_with_key("other", other_org)
        Policy.objects.create(agent=other_agent)
        self.client.force_authenticate(user=self.viewer)
        self.assertEqual(self.client.get("/v1/policies/").json()["count"], 1)

    def test_non_member_is_rejected(self):
        outsider = User.objects.create_user("outsider")
        self.client.force_authenticate(user=outsider)
        self.assertEqual(self.client.get("/v1/policies/").status_code, 403)
