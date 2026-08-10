from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.website.serve import get_response, get_response_content

from verityai_saas.services.onboarding import create_workspace
from verityai_saas.www.verityai.integrations import get_context as integrations_context
from verityai_saas.tests.cleanup import cleanup_all_test_fixtures, cleanup_test_workspace


class TestCustomerPortalRoutes(FrappeTestCase):
	@classmethod
	def tearDownClass(cls):
		super().tearDownClass()
		cleanup_all_test_fixtures()

	def setUp(self):
		frappe.set_user("Administrator")
		token = frappe.generate_hash(length=8).lower()
		self.user = frappe.get_doc(
			{
				"doctype": "User",
				"email": f"portal-{token}@example.com",
				"first_name": "Portal",
				"last_name": "Tester",
				"user_type": "Website User",
				"send_welcome_email": 0,
			}
		).insert(ignore_permissions=True).name
		self.created = create_workspace(
			self.user,
			f"Portal Account {token}",
			f"Portal Workspace {token}",
		)

	def tearDown(self):
		super().tearDown()
		cleanup_test_workspace(self.created["workspace"], users=[self.user], engine_tenant=self.created["engine_tenant"])

	def test_customer_portal_uses_non_desk_route(self):
		frappe.set_user(self.user)
		content = get_response_content("/verityai/dashboard")
		self.assertIn('data-verity-page="dashboard"', content)
		self.assertNotIn('window.csrf_token=""', content)
		self.assertIn("/verityai/assistant", content)
		self.assertIn("/verityai/quotes", content)
		self.assertIn("/verityai/commerce", content)
		self.assertIn("/verityai/crm", content)
		self.assertIn("/verityai/health", content)
		self.assertIn("/verityai/account", content)
		self.assertNotIn("/verityai/integrations", content)
		self.assertNotIn('href="/app/assistant"', content)
		quote_content = get_response_content("/verityai/quotes")
		self.assertIn('data-verity-page="quotes"', quote_content)
		commerce_content = get_response_content("/verityai/commerce")
		self.assertIn('data-verity-page="commerce"', commerce_content)
		crm_content = get_response_content("/verityai/crm")
		self.assertIn('data-verity-page="crm"', crm_content)
		health_content = get_response_content("/verityai/health")
		self.assertIn('data-verity-page="health"', health_content)

	def test_onboarding_returns_safe_dashboard_url(self):
		self.assertTrue(self.created["dashboard_url"].startswith("/verityai/dashboard"))

	def test_workspace_owner_receives_portal_only_role(self):
		self.assertIn("VerityAI Customer Owner", frappe.get_roles(self.user))
		self.assertEqual(frappe.db.get_value("Role", "VerityAI Customer Owner", "desk_access"), 0)

	def test_integration_configuration_page_is_operator_only(self):
		frappe.set_user(self.user)
		with self.assertRaises(frappe.PermissionError):
			integrations_context(frappe._dict())
		frappe.set_user("Administrator")
		with patch("verityai_saas.services.permissions.frappe.get_roles", return_value=["VerityAI Operator"]):
			with self.assertRaises(frappe.PermissionError):
				integrations_context(frappe._dict())
		context = frappe._dict()
		integrations_context(context)
		self.assertEqual(context.portal_page, "integrations")

	def test_platform_admin_page_renders_as_utf8(self):
		frappe.set_user("Administrator")
		content = get_response_content("/verityai/admin")
		self.assertIn('id="va-admin-content"', content)
		self.assertIn("/assets/verityai_saas/js/admin.js?v=0.1.1", content)
		self.assertNotIn('window.csrf_token=""', content)

	def test_guest_is_redirected_to_login(self):
		frappe.set_user("Guest")
		response = get_response("/verityai/dashboard")
		self.assertIn(response.status_code, {301, 302, 303, 307, 308})
		self.assertIn("/login", response.headers.get("Location", ""))
