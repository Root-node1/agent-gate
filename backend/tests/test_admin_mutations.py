from unittest.mock import Mock

from django.contrib.admin.sites import AdminSite
from django.test import RequestFactory, SimpleTestCase

from apps.agents.admin import AgentAdmin, ApiKeyAdmin, ApiKeyInline
from apps.agents.models import Agent, ApiKey
from apps.policies.admin import MerchantRuleAdmin, MerchantRuleInline, PolicyAdmin
from apps.policies.models import MerchantRule, Policy
from apps.spend.admin import SpendRequestAdmin
from apps.spend.models import SpendRequest


class AdminMutationProtectionTests(SimpleTestCase):
    def setUp(self):
        self.request = RequestFactory().get("/admin/")
        self.request.user = Mock()
        self.request.user.has_perm.return_value = True
        self.site = AdminSite()

    def assert_all_fields_read_only(self, model_admin, model):
        fields = {field.name for field in model._meta.fields}
        self.assertTrue(fields.issubset(set(model_admin.get_readonly_fields(self.request))))
        self.assertTrue(model_admin.has_view_permission(self.request))

    def test_agent_and_inline_api_keys_are_inspectable_but_immutable(self):
        agent_admin = AgentAdmin(Agent, self.site)
        key_inline = ApiKeyInline(Agent, self.site)
        key_admin = ApiKeyAdmin(ApiKey, self.site)

        self.assert_all_fields_read_only(agent_admin, Agent)
        self.assertFalse(agent_admin.has_add_permission(self.request))
        self.assertFalse(agent_admin.has_delete_permission(self.request))
        self.assert_all_fields_read_only(key_inline, ApiKey)
        self.assertFalse(key_inline.has_add_permission(self.request))
        self.assertFalse(key_inline.has_delete_permission(self.request))
        self.assert_all_fields_read_only(key_admin, ApiKey)
        self.assertFalse(key_admin.has_add_permission(self.request))
        self.assertFalse(key_admin.has_delete_permission(self.request))

    def test_policy_and_merchant_rules_are_inspectable_but_immutable(self):
        policy_admin = PolicyAdmin(Policy, self.site)
        rule_inline = MerchantRuleInline(Policy, self.site)
        rule_admin = MerchantRuleAdmin(MerchantRule, self.site)

        self.assert_all_fields_read_only(policy_admin, Policy)
        self.assertFalse(policy_admin.has_add_permission(self.request))
        self.assertFalse(policy_admin.has_delete_permission(self.request))
        self.assert_all_fields_read_only(rule_inline, MerchantRule)
        self.assertFalse(rule_inline.has_add_permission(self.request))
        self.assertFalse(rule_inline.has_delete_permission(self.request))
        self.assert_all_fields_read_only(rule_admin, MerchantRule)
        self.assertFalse(rule_admin.has_add_permission(self.request))
        self.assertFalse(rule_admin.has_delete_permission(self.request))

    def test_spend_requests_are_inspectable_but_immutable(self):
        spend_admin = SpendRequestAdmin(SpendRequest, self.site)

        self.assert_all_fields_read_only(spend_admin, SpendRequest)
        self.assertFalse(spend_admin.has_add_permission(self.request))
        self.assertFalse(spend_admin.has_delete_permission(self.request))
