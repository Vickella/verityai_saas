from unittest.mock import patch

import frappe
from frappe.model.document import Document
from frappe.tests.utils import FrappeTestCase

from verityai_saas import setup_doctypes
from verityai_saas.api import quotes
from verityai_saas.services import engine
from verityai_saas.services.onboarding import create_workspace
from verityai_saas.tests.cleanup import cleanup_all_test_fixtures, cleanup_test_workspace


class TestQuoteApprovalPortal(FrappeTestCase):
	@classmethod
	def tearDownClass(cls):
		super().tearDownClass()
		cleanup_all_test_fixtures()

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		frappe.set_user("Administrator")
		setup_doctypes.install()

	def setUp(self):
		frappe.set_user("Administrator")
		token = frappe.generate_hash(length=8).lower()
		self.owner = self.create_user(f"quote-owner-{token}@example.com")
		self.other = self.create_user(f"quote-other-{token}@example.com")
		self.created = create_workspace(
			self.owner,
			f"Quote Account {token}",
			f"Quote Workspace {token}",
		)
		self.workspace = self.created["workspace"]
		self.tenant = self.created["engine_tenant"]

	def tearDown(self):
		super().tearDown()
		cleanup_test_workspace(self.workspace, users=[self.owner, self.other])

	def create_user(self, email):
		return frappe.get_doc(
			{
				"doctype": "User",
				"email": email,
				"first_name": "Quote",
				"last_name": "Tester",
				"user_type": "Website User",
				"send_welcome_email": 0,
			}
		).insert(ignore_permissions=True).name

	def create_request(self, tenant=None, status="Pending"):
		return frappe.get_doc(
			{
				"doctype": "AI Quotation Request",
				"tenant": tenant or self.tenant,
				"customer_name": "Portal Customer",
				"client_email": "client@example.com",
				"items": frappe.as_json([{"item_code": "SERVICE", "qty": 1, "rate": 100}]),
				"estimated_total": 100,
				"status": status,
			}
		).insert(ignore_permissions=True)

	def test_quote_requests_are_tenant_scoped_and_safe(self):
		request = self.create_request()
		other_tenant = frappe.get_doc(
			{
				"doctype": "AI Tenant",
				"tenant_name": f"other-{frappe.generate_hash(length=8)}",
				"assistant_name": "Other",
				"active": 1,
			}
		).insert(ignore_permissions=True)
		self.create_request(other_tenant.name)

		rows = engine.get_workspace_quote_requests(self.workspace)

		self.assertEqual([row.name for row in rows], [request.name])
		self.assertNotIn("items", rows[0])
		self.assertNotIn("tenant", rows[0])

	def test_non_member_cannot_list_quote_requests(self):
		frappe.set_user(self.other)
		response = quotes.list_requests(self.workspace)
		self.assertFalse(response["success"])
		self.assertEqual(response["code"], "WORKSPACE_FORBIDDEN")

	def test_approval_delegates_to_engine_document_hook(self):
		request = self.create_request()

		with patch.object(Document, "save", autospec=True) as save, patch.object(
			Document, "reload", autospec=True
		):
			result = engine.approve_workspace_quote(self.workspace, request.name, "Approved in portal")

		self.assertEqual(result["status"], "Approved")
		self.assertEqual(result["approval_notes"], "Approved in portal")
		save.assert_called_once()
		self.assertTrue(save.call_args.kwargs["ignore_permissions"])

	def test_cross_tenant_quote_cannot_be_approved(self):
		other_tenant = frappe.get_doc(
			{
				"doctype": "AI Tenant",
				"tenant_name": f"other-{frappe.generate_hash(length=8)}",
				"assistant_name": "Other",
				"active": 1,
			}
		).insert(ignore_permissions=True)
		request = self.create_request(other_tenant.name)

		with self.assertRaises(frappe.DoesNotExistError):
			engine.approve_workspace_quote(self.workspace, request.name)
