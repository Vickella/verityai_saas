from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from verityai_saas import setup_doctypes
from verityai_saas.services import entitlements, onboarding, usage, whatsapp
from verityai_saas.tests.cleanup import cleanup_all_test_fixtures, cleanup_test_workspace


class TestEntitlements(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		frappe.set_user("Administrator")
		setup_doctypes.install()

	@classmethod
	def tearDownClass(cls):
		super().tearDownClass()
		cleanup_all_test_fixtures()

	def setUp(self):
		frappe.set_user("Administrator")
		self.token = frappe.generate_hash(length=8).lower()
		self.owner = frappe.get_doc({
			"doctype": "User", "email": f"entitlement-owner-{self.token}@example.com",
			"first_name": "Entitlement", "last_name": "Tester", "user_type": "Website User",
			"send_welcome_email": 0,
		}).insert(ignore_permissions=True).name
		self.created = onboarding.create_workspace(
			self.owner, f"Entitlement Account {self.token}", f"Entitlement Workspace {self.token}"
		)
		self.workspace = self.created["workspace"]
		self.tenant = self.created["engine_tenant"]
		self.plan = self._create_plan()

	def tearDown(self):
		super().tearDown()
		cleanup_test_workspace(self.workspace, users=[self.owner], engine_tenant=self.tenant, commit=False)
		if frappe.db.exists("VerityAI Plan", self.plan):
			frappe.delete_doc("VerityAI Plan", self.plan, ignore_permissions=True, force=True)
		frappe.db.commit()

	def _create_plan(self, **overrides):
		values = {
			"doctype": "VerityAI Plan", "plan_name": f"Entitlement Plan {self.token}",
			"plan_code": f"ENT-{self.token.upper()}", "active": 1, "currency": "USD",
			"max_workspaces": 1, "max_assistants": 1, "monthly_token_limit": 1000,
			"monthly_web_conversations": 1, "monthly_whatsapp_messages": 1,
			"monthly_email_sends": 1, "can_use_whatsapp_button": 1,
			"can_use_whatsapp_ai": 1, "can_use_email_notifications": 1,
			"can_use_quotation_workflow": 1,
		}
		values.update(overrides)
		return frappe.get_doc(values).insert(ignore_permissions=True).name

	def _activate_plan(self):
		frappe.db.set_value("VerityAI Subscription", self.created["subscription"], {
			"plan": self.plan, "status": "Active",
		})
		frappe.db.set_value("VerityAI Workspace", self.workspace, "status", "Active")
		frappe.db.set_value("VerityAI Usage Wallet", self.created["wallet"], {
			"tokens_remaining": 1000, "status": "Normal",
		})

	def _usage_log(self, platform="Web", session=None):
		return frappe.get_doc({
			"doctype": "AI Usage Log", "tenant": self.tenant, "chat_session": session,
			"platform": platform, "input_tokens": 2, "output_tokens": 3,
			"total_tokens": 5, "status": "Success",
		}).insert(ignore_permissions=True)

	def test_non_saas_tenant_is_not_blocked(self):
		self.assertEqual(entitlements.check_engine_request("external-tenant", "Web"), {"allowed": True})

	def test_inactive_subscription_and_exhausted_wallet_are_blocked(self):
		frappe.db.set_value("VerityAI Subscription", self.created["subscription"], "status", "Suspended")
		self.assertEqual(entitlements.check_engine_request(self.tenant, "Web")["code"], "SUBSCRIPTION_INACTIVE")
		frappe.db.set_value("VerityAI Subscription", self.created["subscription"], "status", "Trial")
		frappe.db.set_value("VerityAI Usage Wallet", self.created["wallet"], "tokens_remaining", 0)
		self.assertEqual(entitlements.check_engine_request(self.tenant, "Web")["code"], "WALLET_EXHAUSTED")

	def test_expired_trial_is_synchronously_disabled(self):
		frappe.db.set_value("VerityAI Subscription", self.created["subscription"], {
			"status": "Trial", "trial_end": frappe.utils.add_days(frappe.utils.today(), -1),
		})
		result = entitlements.check_engine_request(self.tenant, "Web")
		self.assertEqual(result["code"], "TRIAL_EXPIRED")
		self.assertEqual(frappe.db.get_value("AI Tenant", self.tenant, "active"), 0)
		self.assertEqual(frappe.db.get_value("VerityAI Usage Wallet", self.created["wallet"], "status"), "Suspended")

	def test_paid_plan_channel_feature_and_quota_are_enforced(self):
		self._activate_plan()
		frappe.db.set_value("VerityAI Plan", self.plan, "can_use_whatsapp_ai", 0)
		self.assertEqual(entitlements.check_engine_request(self.tenant, "WhatsApp")["code"], "CHANNEL_NOT_INCLUDED")
		frappe.db.set_value("VerityAI Plan", self.plan, "can_use_whatsapp_ai", 1)
		session = frappe.get_doc({
			"doctype": "AI Chat Session", "session_id": frappe.generate_hash(), "tenant": self.tenant,
			"platform": "Web", "status": "Open", "chat_history": "[]",
		}).insert(ignore_permissions=True)
		self._usage_log(session=session.name)
		self.assertEqual(entitlements.check_engine_request(self.tenant, "Web")["code"], "CHANNEL_QUOTA_EXHAUSTED")

	def test_trial_respects_explicit_plan_feature_flags(self):
		frappe.db.set_value("VerityAI Subscription", self.created["subscription"], {"plan": self.plan, "status": "Trial"})
		frappe.db.set_value("VerityAI Plan", self.plan, "can_use_whatsapp_ai", 0)
		context = entitlements.workspace_context(workspace_name=self.workspace)
		self.assertFalse(entitlements.feature_allowed(context, "can_use_whatsapp_ai"))
		frappe.db.set_value("VerityAI Plan", self.plan, "can_use_whatsapp_ai", 1)
		context = entitlements.workspace_context(workspace_name=self.workspace)
		self.assertTrue(entitlements.feature_allowed(context, "can_use_whatsapp_ai"))
	def test_email_allowance_is_period_scoped(self):
		self._activate_plan()
		self.assertEqual(entitlements.email_delivery_allowance(self.workspace), 1)
		frappe.get_doc({
			"doctype": "VerityAI Email Delivery Log", "workspace": self.workspace,
			"notification_type": "Test", "recipient": self.owner, "subject": "Test", "status": "Sent",
		}).insert(ignore_permissions=True)
		self.assertEqual(entitlements.email_delivery_allowance(self.workspace), 0)
		frappe.db.set_value("VerityAI Plan", self.plan, "can_use_email_notifications", 0)
		self.assertEqual(entitlements.email_delivery_allowance(self.workspace), 0)

	def test_usage_sync_updates_all_wallet_channel_counters(self):
		session = frappe.get_doc({
			"doctype": "AI Chat Session", "session_id": frappe.generate_hash(), "tenant": self.tenant,
			"platform": "Web", "status": "Open", "chat_history": "[]",
		}).insert(ignore_permissions=True)
		self._usage_log("Web", session.name)
		self._usage_log("Web", session.name)
		self._usage_log("WhatsApp", session.name)
		frappe.get_doc({
			"doctype": "VerityAI Email Delivery Log", "workspace": self.workspace,
			"notification_type": "Test", "recipient": self.owner, "subject": "Test", "status": "Sent",
		}).insert(ignore_permissions=True)
		usage.sync_workspace_usage(self.workspace)
		wallet = frappe.db.get_value("VerityAI Usage Wallet", self.created["wallet"], [
			"web_conversations_used", "whatsapp_messages_used", "email_sends_used",
		], as_dict=True)
		self.assertEqual(wallet.web_conversations_used, 1)
		self.assertEqual(wallet.whatsapp_messages_used, 1)
		self.assertEqual(wallet.email_sends_used, 1)

	def test_plan_capacity_blocks_another_workspace(self):
		self._activate_plan()
		with self.assertRaises(frappe.ValidationError):
			entitlements.assert_account_capacity(self.created["account"])

	def test_whatsapp_configuration_obeys_paid_plan_feature(self):
		self._activate_plan()
		frappe.db.set_value("VerityAI Plan", self.plan, "can_use_whatsapp_ai", 0)
		with self.assertRaises(frappe.PermissionError):
			whatsapp.configure(self.workspace, {"mode": "Full AI Automation"})
