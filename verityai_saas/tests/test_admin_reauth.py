from unittest.mock import patch

import frappe
from frappe.auth import LoginAttemptTracker
from frappe.tests.utils import FrappeTestCase
from frappe.website.serve import get_response_content

from verityai_saas.api import admin as admin_api
from verityai_saas.api import admin_auth
from verityai_saas.services.admin_reauth import (
	UNLOCK_SECONDS,
	_attempt_key,
	clear_admin_reauthentication,
	is_admin_reauthenticated,
	mark_admin_reauthenticated,
)


class TestAdminReauthentication(FrappeTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		clear_admin_reauthentication()

	def tearDown(self):
		frappe.set_user("Administrator")
		clear_admin_reauthentication()
		LoginAttemptTracker(_attempt_key()).add_success_attempt()
		super().tearDown()

	def test_locked_page_does_not_render_operator_console(self):
		content = get_response_content("/verityai/admin")
		self.assertIn('id="va-admin-unlock-form"', content)
		self.assertNotIn('id="va-admin-content"', content)
		response = admin_api.dashboard()
		self.assertFalse(response["success"])
		self.assertEqual(response["code"], "AUTH_REQUIRED")

	def test_successful_password_check_unlocks_only_current_session(self):
		with patch("verityai_saas.services.admin_reauth.check_password", return_value="Administrator") as verifier:
			response = admin_auth.unlock("correct-password")
		self.assertTrue(response["success"])
		self.assertEqual(response["data"]["expires_in_seconds"], UNLOCK_SECONDS)
		verifier.assert_called_once_with("Administrator", "correct-password", delete_tracker_cache=False)
		self.assertTrue(is_admin_reauthenticated())
		self.assertIn('id="va-admin-content"', get_response_content("/verityai/admin"))
		admin_auth.lock()
		self.assertFalse(is_admin_reauthenticated())

	def test_bad_password_never_unlocks_session(self):
		with patch("verityai_saas.services.admin_reauth.check_password", side_effect=frappe.AuthenticationError("bad")):
			response = admin_auth.unlock("wrong-password")
		self.assertFalse(response["success"])
		self.assertFalse(is_admin_reauthenticated())

	def test_failed_password_attempts_are_rate_limited(self):
		with patch("verityai_saas.services.admin_reauth.check_password", side_effect=frappe.AuthenticationError("bad")) as verifier:
			for _ in range(5):
				self.assertFalse(admin_auth.unlock("wrong-password")["success"])
			blocked = admin_auth.unlock("wrong-password")
		self.assertFalse(blocked["success"])
		self.assertIn("Too many failed attempts", blocked["error"])
		self.assertEqual(verifier.call_count, 5)

	def test_unlock_is_bound_to_session_fingerprint(self):
		mark_admin_reauthenticated()
		self.assertTrue(is_admin_reauthenticated())
		original_sid = frappe.session.sid
		try:
			frappe.session.sid = f"different-{frappe.generate_hash(length=8)}"
			self.assertFalse(is_admin_reauthenticated())
		finally:
			frappe.session.sid = original_sid
