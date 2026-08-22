from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from verityai_saas import setup_doctypes
from verityai_saas.api import quotes
from verityai_saas.services import commerce
from verityai_saas.services.onboarding import create_workspace
from verityai_saas.tests.cleanup import cleanup_all_test_fixtures, cleanup_test_workspace


class TestQuoteApprovalPortal(FrappeTestCase):
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
		self.owner = self.create_user(f"quote-owner-{token}@example.com")
		self.other_owner = self.create_user(f"quote-other-{token}@example.com")
		self.created = create_workspace(self.owner, f"Quote Account {token}", f"Quote Workspace {token}")
		self.other = create_workspace(self.other_owner, f"Other Quote {token}", f"Other Quote Workspace {token}")
		self.workspace = self.created["workspace"]
		self.product = commerce.save_product(self.workspace, {
			"item_code": "VERITYPACK", "item_name": "VerityPack", "standard_rate": 100, "currency": "USD",
		})

	def tearDown(self):
		super().tearDown()
		cleanup_test_workspace(self.workspace, users=[self.owner], engine_tenant=self.created["engine_tenant"], commit=False)
		cleanup_test_workspace(self.other["workspace"], users=[self.other_owner], engine_tenant=self.other["engine_tenant"])

	def create_user(self, email):
		return frappe.get_doc({
			"doctype": "User", "email": email, "first_name": "Quote", "last_name": "Tester",
			"user_type": "Website User", "send_welcome_email": 0,
		}).insert(ignore_permissions=True).name

	def ai_request(self, item="VERITYPACK"):
		return commerce.handle_ai_quotation_request(
			self.created["engine_tenant"], "TEST ABC Ltd",
			[{"item_code": item, "qty": 1}], client_email="buyer@example.com",
			notes="Three users, manufacturing, all modules, replacing Odoo.", source_channel="Web",
		)

	def test_ai_request_creates_visible_native_pending_quotation(self):
		created = self.ai_request()
		self.assertTrue(created["success"])
		frappe.set_user(self.owner)
		response = quotes.list_requests(self.workspace)
		self.assertTrue(response["success"])
		self.assertEqual([row.name for row in response["data"]], [created["quotation"]])
		self.assertEqual(response["data"][0].status, "Pending Approval")

	def test_unknown_ai_scope_is_staged_for_review_without_false_success(self):
		created = self.ai_request("All modules including manufacturing")
		self.assertTrue(created["success"])
		quote = commerce.get_quotation(self.workspace, created["quotation"])
		self.assertEqual(quote["items"][0]["description"], "All modules including manufacturing")
		self.assertEqual(quote.status, "Pending Approval")

	def test_owner_can_edit_approve_email_and_generate_public_pdf(self):
		created = self.ai_request("All modules including manufacturing")
		frappe.set_user(self.owner)
		quote = quotes.detail(self.workspace, created["quotation"])["data"]
		values = {
			"customer": quote.customer, "transaction_date": quote.transaction_date,
			"valid_till": quote.valid_till, "price_list": quote.price_list, "currency": quote.currency,
			"discount_amount": 0, "tax_rate": 0, "notes": "Reviewed manufacturing scope",
			"items": [{"product": quote["items"][0]["product"], "qty": 1, "rate": 450, "discount_percent": 0}],
		}
		updated = quotes.update(self.workspace, quote.name, frappe.as_json(values))
		self.assertTrue(updated["success"])
		self.assertEqual(updated["data"]["items"][0]["description"], "All modules including manufacturing")
		with patch("frappe.sendmail") as sendmail:
			approved = quotes.approve(self.workspace, quote.name)
		self.assertTrue(approved["success"])
		self.assertEqual(approved["data"]["quotation"].status, "Sent")
		self.assertIn("download_public_quotation", approved["data"]["pdf_url"])
		sendmail.assert_called_once()
		self.assertEqual(sendmail.call_args.kwargs["recipients"], ["buyer@example.com"])

	def test_reject_and_cross_tenant_access_are_controlled(self):
		created = self.ai_request()
		frappe.set_user(self.other_owner)
		denied = quotes.detail(self.workspace, created["quotation"])
		self.assertFalse(denied["success"])
		self.assertEqual(denied["code"], "WORKSPACE_FORBIDDEN")
		frappe.set_user(self.owner)
		rejected = quotes.reject(self.workspace, created["quotation"], "Scope needs clarification")
		self.assertTrue(rejected["success"])
		self.assertEqual(rejected["data"].status, "Rejected")
