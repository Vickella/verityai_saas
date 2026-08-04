from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from verityai_saas import setup_doctypes
from verityai_saas.api import email as email_api
from verityai_saas.services.notifications import (
	send_provider_failure_notification,
	send_quote_request_notification,
)
from verityai_saas.services.onboarding import create_workspace
from verityai_saas.tests.cleanup import cleanup_all_test_fixtures, cleanup_test_workspace


class TestNotificationManagement(FrappeTestCase):
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
		token = frappe.generate_hash(length=8).lower()
		self.owner = self.create_user(f"notify-owner-{token}@example.com")
		self.other = self.create_user(f"notify-other-{token}@example.com")
		created = create_workspace(
			self.owner,
			f"Notification Account {token}",
			f"Notification Workspace {token}",
		)
		self.workspace = created["workspace"]
		self.tenant = created["engine_tenant"]
		self.setting = frappe.db.get_value(
			"VerityAI Notification Setting", {"workspace": self.workspace}, "name"
		)

	def tearDown(self):
		super().tearDown()
		cleanup_test_workspace(
			self.workspace,
			users=[self.owner, self.other],
			engine_tenant=self.tenant,
		)

	def create_user(self, email):
		return frappe.get_doc(
			{
				"doctype": "User",
				"email": email,
				"first_name": "Notification",
				"last_name": "Tester",
				"user_type": "Website User",
				"send_welcome_email": 0,
			}
		).insert(ignore_permissions=True).name

	def test_owner_can_update_all_settings_with_normalized_recipients(self):
		frappe.set_user(self.owner)
		response = email_api.update(
			self.workspace,
			{
				"notification_email": self.owner,
				"reply_to_email": "reply@example.com",
				"alert_recipients": "alerts@example.com; second@example.com\nalerts@example.com",
				"lead_notifications_enabled": 0,
				"human_handoff_alerts_enabled": 0,
				"quote_request_alerts_enabled": 1,
				"usage_warning_alerts_enabled": 0,
				"provider_failure_alerts_enabled": 1,
				"daily_summary_enabled": 1,
				"status": "Disabled",
			},
		)

		self.assertTrue(response["success"])
		self.assertEqual(response["data"]["alert_recipients"], "alerts@example.com, second@example.com")
		self.assertEqual(response["data"]["status"], "Disabled")
		self.assertEqual(response["data"]["human_handoff_alerts_enabled"], 0)

	def test_invalid_email_and_non_manager_are_rejected(self):
		frappe.set_user(self.owner)
		response = email_api.update(self.workspace, {"notification_email": "not-an-email"})
		self.assertFalse(response["success"])

		frappe.set_user(self.other)
		response = email_api.send_test(self.workspace)
		self.assertFalse(response["success"])
		self.assertEqual(response["code"], "WORKSPACE_FORBIDDEN")

	def test_quote_request_alert_is_sent_once(self):
		frappe.db.set_value("VerityAI Notification Setting", self.setting, {
			"notification_email": self.owner,
			"alert_recipients": "",
			"email_branding_name": "<Example>",
			"email_footer": "<Footer>",
			"status": "Active",
			"quote_request_alerts_enabled": 1,
		})
		doc = frappe._dict({
			"name": "QUOTE-NOTIFY-1",
			"tenant": self.tenant,
			"status": "Pending",
			"customer_name": "Example Customer",
			"estimated_total": 250,
		})

		with patch("frappe.sendmail") as sendmail:
			first = send_quote_request_notification(doc)
			second = send_quote_request_notification(doc)

		self.assertEqual(len(first), 1)
		self.assertEqual(second, [])
		sendmail.assert_called_once()
		self.assertIn("&lt;Example&gt;", sendmail.call_args.kwargs["message"])
		self.assertIn("&lt;Footer&gt;", sendmail.call_args.kwargs["message"])

	def test_only_open_system_alerts_trigger_provider_email(self):
		frappe.db.set_value("VerityAI Notification Setting", self.setting, {
			"notification_email": self.owner,
			"alert_recipients": "",
			"status": "Active",
			"provider_failure_alerts_enabled": 1,
		})
		doc = frappe._dict({
			"name": "ALERT-NOTIFY-1",
			"tenant": self.tenant,
			"alert_type": "System",
			"status": "Open",
			"summary": "Provider request failed.",
		})

		with patch("frappe.sendmail") as sendmail:
			first = send_provider_failure_notification(doc)
			second = send_provider_failure_notification(doc)
			not_provider = send_provider_failure_notification(
				frappe._dict({**doc, "name": "ALERT-NOTIFY-2", "alert_type": "Usage"})
			)

		self.assertEqual(len(first), 1)
		self.assertEqual(second, [])
		self.assertEqual(not_provider, [])
		sendmail.assert_called_once()

	def test_failed_email_delivery_can_be_retried(self):
		log = frappe.get_doc({
			"doctype": "VerityAI Email Delivery Log", "workspace": self.workspace,
			"notification_type": "Test", "recipient": self.owner, "subject": "Retry me",
			"message": "<p>Original safe message</p>", "status": "Failed", "error": "Temporary SMTP error",
		}).insert(ignore_permissions=True)
		frappe.set_user(self.owner)
		with patch("frappe.sendmail") as sendmail:
			response = email_api.retry(self.workspace, log.name)
		self.assertTrue(response["success"])
		self.assertEqual(response["data"]["status"], "Sent")
		self.assertEqual(frappe.db.get_value("VerityAI Email Delivery Log", log.name, "error"), None)
		self.assertEqual(sendmail.call_args.kwargs["message"], "<p>Original safe message</p>")