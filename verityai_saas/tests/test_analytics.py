import io
import zipfile
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, now_datetime, today

from verityai_saas import setup_doctypes
from verityai_saas.api import analytics as analytics_api
from verityai_saas.services import analytics, billing
from verityai_saas.services.admin_reauth import mark_admin_reauthenticated
from verityai_saas.services.onboarding import create_workspace
from verityai_saas.tests.cleanup import cleanup_all_test_fixtures, cleanup_test_workspace


class TestAnalyticsAndReports(FrappeTestCase):
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
		self.owner = frappe.get_doc({"doctype": "User", "email": f"analytics-owner-{token}@example.com", "first_name": "Analytics", "last_name": "Owner", "user_type": "Website User", "send_welcome_email": 0}).insert(ignore_permissions=True).name
		self.created = create_workspace(self.owner, f"Analytics Account {token}", f"Analytics Workspace {token}")
		self.workspace = self.created["workspace"]
		self.tenant = self.created["engine_tenant"]
		self.session = frappe.get_doc({"doctype": "AI Chat Session", "tenant": self.tenant, "session_id": frappe.generate_hash(), "platform": "Web", "user_identifier": "visitor", "status": "Open", "chat_history": "[]"}).insert(ignore_permissions=True)
		frappe.get_doc({"doctype": "AI Usage Log", "tenant": self.tenant, "chat_session": self.session.name, "platform": "Web", "input_tokens": 10, "output_tokens": 5, "total_tokens": 15, "estimated_cost": 0.01, "status": "Success"}).insert(ignore_permissions=True)
		frappe.get_doc({"doctype": "AI Lead", "tenant": self.tenant, "lead_name": "=Formula Lead", "source_channel": "Web", "status": "Won", "chat_session": self.session.name}).insert(ignore_permissions=True)
		billing.create_billing_event(self.workspace, "Payment", 20, "Completed", provider_reference="ANALYTICS-20")

	def tearDown(self):
		super().tearDown()
		frappe.db.delete("VerityAI Report Schedule", {"workspace": self.workspace})
		cleanup_test_workspace(self.workspace, users=[self.owner], engine_tenant=self.tenant)

	def test_workspace_time_series_and_zip_export(self):
		frappe.set_user(self.owner)
		response = analytics_api.get(self.workspace)
		self.assertTrue(response["success"])
		data = response["data"]
		self.assertEqual(len(data["usage"]), 30)
		self.assertEqual(sum(row["tokens"] for row in data["usage"]), 15)
		self.assertEqual(data["channels"]["Web"], 1)
		archive_bytes = analytics.workspace_export(self.workspace)
		with zipfile.ZipFile(io.BytesIO(archive_bytes)) as archive:
			self.assertEqual(set(archive.namelist()), {"usage-timeseries.csv", "leads.csv", "conversations.csv", "usage-events.csv", "billing.csv"})
			self.assertIn("\t=Formula Lead", archive.read("leads.csv").decode("utf-8-sig"))

	def test_report_range_is_bounded(self):
		with self.assertRaises(frappe.ValidationError):
			analytics.workspace_analytics(self.workspace, add_days(today(), -400), today())

	def test_operator_schedule_sends_attachment_and_updates_next_run(self):
		created = analytics_api.create_schedule({"report_name": "Weekly workspace report", "report_type": "Workspace Analytics", "workspace": self.workspace, "recipients": "ops@example.com", "frequency": "Weekly", "active": 1})
		self.assertTrue(created["success"])
		schedule = created["data"]["schedule"]
		frappe.db.set_value("VerityAI Report Schedule", schedule, "next_send_on", add_days(now_datetime(), -1))
		with patch("frappe.sendmail") as sendmail:
			analytics.send_due_reports()
		sendmail.assert_called_once()
		attachment = sendmail.call_args.kwargs["attachments"][0]
		self.assertTrue(attachment["fname"].endswith(".zip"))
		self.assertEqual(frappe.db.get_value("VerityAI Report Schedule", schedule, "last_status"), "Sent")

	def test_customer_cannot_manage_operator_report_schedules(self):
		frappe.set_user(self.owner)
		response = analytics_api.create_schedule({"report_name": "No", "report_type": "Operator Summary", "recipients": self.owner, "frequency": "Daily"})
		self.assertFalse(response["success"])
		self.assertEqual(response["code"], "WORKSPACE_FORBIDDEN")
