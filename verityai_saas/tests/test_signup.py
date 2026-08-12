from unittest.mock import Mock, patch
from urllib.parse import parse_qs, urlparse

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.website.serve import get_response_content

from verityai_saas.api.signup import register


class TestCustomerSignup(FrappeTestCase):
	def setUp(self):
		frappe.set_user("Guest")

	def tearDown(self):
		frappe.set_user("Administrator")
		super().tearDown()

	def test_signup_page_is_available_to_guests(self):
		content = get_response_content("/verityai/signup")
		self.assertIn('id="signup-form"', content)
		self.assertIn("Create your AI workspace", content)
		self.assertIn('name="password"', content)
		self.assertIn('name="confirm_password"', content)

	@patch("verityai_saas.api.signup.frappe.get_doc")
	def test_registration_creates_user_and_authenticates_before_onboarding(self, get_doc):
		user = get_doc.return_value
		user.name = "owner@example.com"
		login_manager = Mock()
		login_manager.post_login.side_effect = lambda: setattr(frappe.session, "user", "owner@example.com")
		frappe.local.login_manager = login_manager
		original_user = frappe.session.user
		try:
			with patch("verityai_saas.api.signup.frappe.db.exists", return_value=False), patch(
				"verityai_saas.api.signup.frappe.db.get_creation_count", return_value=0
			), patch("verityai_saas.api.signup.frappe.db.savepoint"), patch(
				"verityai_saas.api.signup.frappe.cache"
			):
				response = register(
					"OWNER@EXAMPLE.COM",
					"Workspace Owner",
					"Example & Sons",
					"Secure-test-password-42!",
					"Secure-test-password-42!",
					"Customer Success",
				)
		finally:
			frappe.session.user = original_user
			del frappe.local.login_manager

		self.assertTrue(response["success"], response)
		self.assertTrue(response["data"]["registered"])
		login_manager.authenticate.assert_called_once_with(user="owner@example.com", pwd="Secure-test-password-42!")
		login_manager.post_login.assert_called_once_with()
		user_payload = get_doc.call_args.args[0]
		self.assertEqual(user_payload["email"], "owner@example.com")
		self.assertEqual(user_payload["user_type"], "Website User")
		redirect = urlparse(response["data"]["next_url"])
		self.assertEqual(redirect.path, "/verityai/onboarding")
		self.assertEqual(parse_qs(redirect.query)["business_name"], ["Example & Sons"])
		self.assertEqual(parse_qs(redirect.query)["workspace_name"], ["Customer Success"])
		self.assertTrue(response["data"]["login_url"].startswith("/login?"))

	@patch("verityai_saas.api.signup.frappe.get_doc")
	def test_invalid_registration_does_not_create_user(self, get_doc):
		response = register("not-an-email", "Owner", "Example", "Password-42!", "Password-42!")

		self.assertFalse(response["success"])
		self.assertEqual(response["code"], "VALIDATION_ERROR")
		get_doc.assert_not_called()

	def test_password_confirmation_is_required(self):
		response = register("owner-new@example.com", "Owner", "Example", "Password-42!", "different")
		self.assertFalse(response["success"])
		self.assertIn("do not match", response["error"])

	def test_short_password_is_rejected(self):
		response = register("owner-short@example.com", "Owner", "Example", "short", "short")
		self.assertFalse(response["success"])
		self.assertIn("at least 8", response["error"])
