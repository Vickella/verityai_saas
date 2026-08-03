import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.website.serve import get_response, get_response_content

from verityai_saas.services.onboarding import create_workspace
from verityai_saas.tests.cleanup import cleanup_test_workspace


class TestCustomerPortalRoutes(FrappeTestCase):
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
		cleanup_test_workspace(self.created["workspace"], users=[self.user])
		super().tearDown()

	def test_customer_portal_uses_non_desk_route(self):
		frappe.set_user(self.user)
		content = get_response_content("/verityai/dashboard")
		self.assertIn('data-verity-page="dashboard"', content)
		self.assertIn("/verityai/assistant", content)
		self.assertNotIn('href="/app/assistant"', content)

	def test_onboarding_returns_safe_dashboard_url(self):
		self.assertTrue(self.created["dashboard_url"].startswith("/verityai/dashboard"))

	def test_workspace_owner_receives_portal_only_role(self):
		self.assertIn("VerityAI Customer Owner", frappe.get_roles(self.user))
		self.assertEqual(frappe.db.get_value("Role", "VerityAI Customer Owner", "desk_access"), 0)

	def test_guest_is_redirected_to_login(self):
		frappe.set_user("Guest")
		response = get_response("/verityai/dashboard")
		self.assertIn(response.status_code, {301, 302, 303, 307, 308})
		self.assertIn("/login", response.headers.get("Location", ""))

