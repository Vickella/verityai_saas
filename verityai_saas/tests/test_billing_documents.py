from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, today

from verityai_saas import setup_doctypes
from verityai_saas.api import billing as billing_api
from verityai_saas.services import billing, billing_documents, entitlements
from verityai_saas.services.admin_reauth import mark_admin_reauthenticated
from verityai_saas.services.onboarding import create_workspace
from verityai_saas.tests.cleanup import cleanup_all_test_fixtures, cleanup_test_workspace


class TestBillingDocumentsAndRecovery(FrappeTestCase):
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
		self.owner = frappe.get_doc({
			"doctype": "User", "email": f"billing-owner-{token}@example.com", "first_name": "Billing",
			"last_name": "Owner", "user_type": "Website User", "send_welcome_email": 0,
		}).insert(ignore_permissions=True).name
		self.created = create_workspace(self.owner, f"Billing Account {token}", f"Billing Workspace {token}")
		self.workspace = self.created["workspace"]
		self.tenant = self.created["engine_tenant"]

	def tearDown(self):
		super().tearDown()
		cleanup_test_workspace(self.workspace, users=[self.owner], engine_tenant=self.tenant)

	def test_completed_payment_generates_receipt_and_pdf_download(self):
		payment = billing.create_billing_event(self.workspace, "Payment", 25, "Completed", provider_reference="MANUAL-25")
		receipt = frappe.db.get_value("VerityAI Billing Document", {"billing_event": payment, "document_type": "Receipt"}, "name")
		self.assertTrue(receipt)
		frappe.set_user(self.owner)
		data = billing_api.get(self.workspace)
		self.assertTrue(any(row.name == receipt for row in data["data"]["documents"]))
		with patch("frappe.utils.pdf.get_pdf", return_value=b"%PDF-test"):
			billing_api.download_document(self.workspace, receipt)
		self.assertEqual(frappe.local.response.filecontent, b"%PDF-test")
		self.assertTrue(frappe.local.response.filename.endswith(".pdf"))

	def test_invoice_becomes_paid_when_receipt_is_generated(self):
		payment = billing.create_billing_event(self.workspace, "Payment", 40, "Pending", provider="Paynow")
		invoice = billing_documents.ensure_invoice_for_payment(payment)
		frappe.db.set_value("VerityAI Billing Event", payment, {"status": "Completed", "paid_on": frappe.utils.now_datetime()})
		receipt = billing_documents.ensure_receipt_for_payment(payment)
		self.assertTrue(receipt)
		self.assertEqual(frappe.db.get_value("VerityAI Billing Document", invoice, "status"), "Paid")

	def test_operator_refund_lifecycle_prevents_over_refund(self):
		payment = billing.create_billing_event(self.workspace, "Payment", 50, "Completed", provider_reference="PAY-50")
		requested = billing_api.initiate_refund(self.workspace, payment, 20, "Customer request")
		self.assertTrue(requested["success"])
		refund = requested["data"]["refund"]
		completed = billing_api.complete_refund(self.workspace, refund, "REFUND-20")
		self.assertTrue(completed["success"])
		self.assertTrue(frappe.db.exists("VerityAI Billing Document", {"billing_event": refund, "document_type": "Refund Confirmation"}))
		over = billing_api.initiate_refund(self.workspace, payment, 31, "Too much")
		self.assertFalse(over["success"])

	def test_past_due_grace_keeps_service_then_expires(self):
		subscription = self.created["subscription"]
		frappe.db.set_value("VerityAI Subscription", subscription, {
			"status": "Active", "current_period_end": add_days(today(), -1), "grace_period_end": None,
		})
		billing.check_subscription_expiry()
		self.assertEqual(frappe.db.get_value("VerityAI Subscription", subscription, "status"), "Past Due")
		self.assertEqual(frappe.db.get_value("VerityAI Workspace", self.workspace, "status"), "Active")
		self.assertTrue(entitlements.check_engine_request(self.tenant, "Web")["allowed"])
		frappe.db.set_value("VerityAI Subscription", subscription, "grace_period_end", add_days(today(), -1))
		billing.check_subscription_expiry()
		self.assertEqual(frappe.db.get_value("VerityAI Subscription", subscription, "status"), "Expired")

	def test_payment_reminders_are_daily_deduplicated(self):
		frappe.db.set_value("VerityAI Subscription", self.created["subscription"], {
			"next_billing_date": today(), "amount": 30, "currency": "USD",
		})
		with patch("frappe.sendmail") as sendmail:
			billing.send_payment_reminders()
			billing.send_payment_reminders()
		self.assertEqual(sendmail.call_count, 1)
		self.assertEqual(frappe.db.count("VerityAI Email Delivery Log", {"workspace": self.workspace, "notification_type": "Payment Reminder"}), 1)

	def test_reconciliation_csv_neutralizes_spreadsheet_formulas(self):
		billing.create_billing_event(self.workspace, "Payment", 10, "Completed", provider_reference="=CMD()")
		billing_api.reconciliation_export()
		content = frappe.local.response.filecontent.decode("utf-8-sig")
		self.assertIn("'=CMD()", content)
		self.assertEqual(frappe.local.response.type, "download")
