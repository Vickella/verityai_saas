from unittest.mock import patch
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

	@patch("verityai_saas.api.signup.sign_up", return_value=(1, "Please check your email for verification"))
	def test_registration_delegates_to_frappe_with_local_onboarding_redirect(self, sign_up):
		response = register(
			"OWNER@EXAMPLE.COM",
			"Workspace Owner",
			"Example & Sons",
			"Customer Success",
		)

		self.assertTrue(response["success"])
		self.assertTrue(response["data"]["registered"])
		args = sign_up.call_args.args
		self.assertEqual(args[0], "owner@example.com")
		self.assertEqual(args[1], "Workspace Owner")
		redirect = urlparse(args[2])
		self.assertEqual(redirect.path, "/verityai/onboarding")
		self.assertEqual(parse_qs(redirect.query)["business_name"], ["Example & Sons"])
		self.assertEqual(parse_qs(redirect.query)["workspace_name"], ["Customer Success"])
		self.assertTrue(response["data"]["login_url"].startswith("/login?"))

	@patch("verityai_saas.api.signup.sign_up")
	def test_invalid_registration_does_not_call_frappe_signup(self, sign_up):
		response = register("not-an-email", "Owner", "Example")

		self.assertFalse(response["success"])
		self.assertEqual(response["code"], "VALIDATION_ERROR")
		sign_up.assert_not_called()
