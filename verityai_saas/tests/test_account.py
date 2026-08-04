import frappe
from frappe.tests.utils import FrappeTestCase

from verityai_saas import setup_doctypes
from verityai_saas.api import account as account_api
from verityai_saas.api import onboarding as onboarding_api
from verityai_saas.services import billing
from verityai_saas.services.onboarding import create_workspace
from verityai_saas.tests.cleanup import cleanup_all_test_fixtures, cleanup_test_workspace


class TestAccountManagement(FrappeTestCase):
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
			"doctype": "User", "email": f"account-owner-{self.token}@example.com",
			"first_name": "Account", "last_name": "Owner", "user_type": "Website User",
			"send_welcome_email": 0,
		}).insert(ignore_permissions=True).name
		self.created = create_workspace(self.owner, f"Account Profile {self.token}", f"Primary {self.token}")
		self.workspace = self.created["workspace"]
		self.additional = None
		self.plan = frappe.get_doc({
			"doctype": "VerityAI Plan", "plan_name": f"Multi Workspace {self.token}",
			"plan_code": f"MULTI-{self.token.upper()}", "active": 1, "currency": "USD",
			"max_workspaces": 2, "max_assistants": 2, "monthly_token_limit": 1000,
		}).insert(ignore_permissions=True).name

	def tearDown(self):
		super().tearDown()
		if self.additional and frappe.db.exists("VerityAI Workspace", self.additional["workspace"]):
			cleanup_test_workspace(self.additional["workspace"], users=[], engine_tenant=self.additional["engine_tenant"], commit=False)
		cleanup_test_workspace(self.workspace, users=[self.owner], engine_tenant=self.created["engine_tenant"], commit=False)
		frappe.db.delete("VerityAI Plan", {"name": self.plan})
		frappe.db.commit()

	def test_owner_can_read_and_update_account_profile(self):
		frappe.set_user(self.owner)
		response = account_api.get(self.workspace)
		self.assertTrue(response["success"])
		self.assertEqual(response["data"]["workspace_count"], 1)
		updated = account_api.update(self.workspace, {
			"billing_email": "billing@example.com", "phone": "+263700000000",
			"currency": "USD", "customer_type": "Agency",
		})
		self.assertTrue(updated["success"])
		self.assertEqual(updated["data"]["customer_type"], "Agency")

	def test_additional_workspace_requires_capacity_and_reuses_account(self):
		frappe.set_user(self.owner)
		blocked = onboarding_api.create(
			"ignored", f"Blocked {self.token}", account=self.created["account"]
		)
		self.assertFalse(blocked["success"])
		frappe.set_user("Administrator")
		billing.assign_plan(self.workspace, self.plan, "Active", "Monthly")
		frappe.set_user(self.owner)
		response = onboarding_api.create(
			"ignored", f"Additional {self.token}", account=self.created["account"]
		)
		self.assertTrue(response["success"])
		self.additional = response["data"]
		self.assertEqual(
			frappe.db.get_value("VerityAI Workspace", self.additional["workspace"], "account"),
			self.created["account"],
		)
		self.assertEqual(account_api.get(self.workspace)["data"]["workspace_count"], 2)
