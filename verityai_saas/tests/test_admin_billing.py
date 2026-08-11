import frappe
from frappe.tests.utils import FrappeTestCase

from verityai_saas import setup_doctypes
from verityai_saas.api import admin as admin_api
from verityai_saas.api import billing as billing_api
from verityai_saas.services.admin_reauth import mark_admin_reauthenticated
from verityai_saas.services.onboarding import create_workspace
from verityai_saas.tests.cleanup import cleanup_all_test_fixtures, cleanup_test_workspace
from verityai_saas.www.verityai import admin as admin_page


class TestOperatorBillingConsole(FrappeTestCase):
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
		mark_admin_reauthenticated()
		token = frappe.generate_hash(length=8).lower()
		self.owner = self.create_user(f"ops-owner-{token}@example.com")
		created = create_workspace(
			self.owner,
			f"Operations Account {token}",
			f"Operations Workspace {token}",
		)
		self.workspace = created["workspace"]
		self.tenant = created["engine_tenant"]
		self.plan = frappe.get_doc({
			"doctype": "VerityAI Plan",
			"plan_name": f"Operations Plan {token}",
			"plan_code": f"OPS-{token.upper()}",
			"active": 1,
			"currency": "USD",
			"monthly_price": 40,
			"annual_price": 400,
			"monthly_token_limit": 400000,
			"max_tokens": 1400,
			"max_team_members": 8,
			"max_knowledge_sources": 30,
			"max_allowed_domains": 8,
		}).insert(ignore_permissions=True).name

	def tearDown(self):
		super().tearDown()
		cleanup_test_workspace(
			self.workspace,
			users=[self.owner],
			engine_tenant=self.tenant,
			commit=False,
		)
		frappe.db.delete("VerityAI Plan", {"name": self.plan})
		frappe.db.commit()

	def create_user(self, email):
		return frappe.get_doc({
			"doctype": "User",
			"email": email,
			"first_name": "Operations",
			"last_name": "Tester",
			"user_type": "Website User",
			"send_welcome_email": 0,
		}).insert(ignore_permissions=True).name

	def test_dashboard_bulk_rollup_includes_usage_plans_and_attention_lists(self):
		wallet = frappe.db.get_value("VerityAI Usage Wallet", {"workspace": self.workspace}, "name")
		frappe.db.set_value("VerityAI Usage Wallet", wallet, {
			"opening_token_allowance": 100,
			"tokens_used": 90,
			"tokens_remaining": 10,
			"status": "Warning",
		})
		response = admin_api.dashboard()

		self.assertTrue(response["success"])
		data = response["data"]
		workspace = next(row for row in data["workspaces"] if row.name == self.workspace)
		self.assertEqual(workspace.usage_percent, 90)
		self.assertTrue(any(row["workspace"] == self.workspace for row in data["high_usage"]))
		self.assertTrue(any(plan.name == self.plan for plan in data["plans"]))
		self.assertNotIn("poll_url", frappe.as_json(data))
		self.assertNotIn("gateway_response_json", frappe.as_json(data))

	def test_non_operator_cannot_read_or_mutate_operator_billing(self):
		frappe.set_user(self.owner)
		responses = [
			admin_api.dashboard(),
			admin_api.create_plan({"plan_name": "Nope", "plan_code": "NOPE"}),
			admin_api.configure_paynow({"integration_id": "blocked", "integration_key": "blocked"}),
			billing_api.assign_plan(self.workspace, self.plan),
			billing_api.set_status(self.workspace, "Suspended", "Not allowed"),
			billing_api.manual_event(self.workspace, "Payment", 40, "Completed", "NOPE"),
			billing_api.top_up(self.workspace, 1000, 1, "NOPE"),
		]
		for response in responses:
			self.assertFalse(response["success"])
			self.assertEqual(response["code"], "WORKSPACE_FORBIDDEN")

	def test_plan_and_status_actions_update_engine_and_create_audit_events(self):
		assigned = billing_api.assign_plan(self.workspace, self.plan, "Active", "Annual")
		self.assertTrue(assigned["success"])
		self.assertEqual(
			frappe.db.get_value("VerityAI Subscription", {"workspace": self.workspace}, "plan"),
			self.plan,
		)
		self.assertEqual(frappe.db.get_value("AI Tenant", self.tenant, "active"), 1)
		self.assertEqual(
			frappe.db.get_value("VerityAI Billing Event", assigned["data"]["event"], "event_type"),
			"Subscription Activation",
		)

		suspended = billing_api.set_status(self.workspace, "Suspended", "Manual review")
		self.assertTrue(suspended["success"])
		self.assertEqual(frappe.db.get_value("AI Tenant", self.tenant, "active"), 0)
		event = frappe.get_doc("VerityAI Billing Event", suspended["data"]["event"])
		self.assertEqual(event.event_type, "Adjustment")
		self.assertIn("Manual review", event.provider_reference)
		self.assertIn("Administrator", event.provider_reference)

	def test_manual_payment_requires_amount_and_reference_then_updates_subscription(self):
		invalid_amount = billing_api.manual_event(self.workspace, "Payment", 0, "Completed", "PAY-0")
		invalid_reference = billing_api.manual_event(self.workspace, "Payment", 40, "Completed", "")
		self.assertFalse(invalid_amount["success"])
		self.assertFalse(invalid_reference["success"])

		response = billing_api.manual_event(self.workspace, "Payment", 40, "Completed", "PAY-VALID")
		self.assertTrue(response["success"])
		event = frappe.get_doc("VerityAI Billing Event", response["data"]["event"])
		self.assertEqual(event.status, "Completed")
		self.assertEqual(event.provider_reference, "PAY-VALID")
		self.assertEqual(
			frappe.db.get_value("VerityAI Subscription", {"workspace": self.workspace}, "last_payment_reference"),
			"PAY-VALID",
		)

	def test_operator_top_up_and_admin_page_access(self):
		response = billing_api.top_up(self.workspace, 2500, 5, "OPS-TOPUP")
		self.assertTrue(response["success"])
		self.assertEqual(
			frappe.db.get_value("VerityAI Usage Wallet", {"workspace": self.workspace}, "top_up_tokens"),
			2500,
		)
		context = frappe._dict()
		admin_page.get_context(context)
		self.assertEqual(context.title, "VerityAI Operator Dashboard")

		frappe.set_user(self.owner)
		with self.assertRaises(frappe.PermissionError):
			admin_page.get_context(frappe._dict())
	def test_operator_can_create_edit_and_archive_plan(self):
		code = f"MANAGED-{frappe.generate_hash(length=6).upper()}"
		created = admin_api.create_plan({
			"plan_name": "Managed Plan", "plan_code": code, "active": 1, "currency": "USD",
			"monthly_price": 25, "max_workspaces": 3, "monthly_web_conversations": 100,
			"can_use_whatsapp_ai": 1, "support_level": "Priority",
		})
		self.assertTrue(created["success"])
		plan = created["data"]["name"]
		try:
			updated = admin_api.update_plan(plan, {"monthly_price": 30, "max_workspaces": 4, "can_use_api_access": 1})
			self.assertTrue(updated["success"])
			self.assertEqual(updated["data"]["monthly_price"], 30)
			self.assertEqual(updated["data"]["max_workspaces"], 4)
			archived = admin_api.archive_plan(plan)
			self.assertTrue(archived["success"])
			self.assertEqual(frappe.db.get_value("VerityAI Plan", plan, "active"), 0)
		finally:
			frappe.db.delete("VerityAI Plan", {"name": plan})
