import frappe
from frappe.tests.utils import FrappeTestCase

from verityai_saas import setup_doctypes
from verityai_saas.api import conversations as conversations_api
from verityai_saas.api import leads as leads_api
from verityai_saas.services.onboarding import create_workspace
from verityai_saas.tests.cleanup import cleanup_all_test_fixtures, cleanup_test_workspace


class TestCRMOperations(FrappeTestCase):
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
		self.owner = frappe.get_doc({"doctype": "User", "email": f"crm-owner-{token}@example.com", "first_name": "CRM", "last_name": "Owner", "user_type": "Website User", "send_welcome_email": 0}).insert(ignore_permissions=True).name
		self.created = create_workspace(self.owner, f"CRM Account {token}", f"CRM Workspace {token}")
		self.workspace = self.created["workspace"]
		self.tenant = self.created["engine_tenant"]
		frappe.db.set_value("VerityAI Notification Setting", {"workspace": self.workspace}, "human_handoff_alerts_enabled", 0)

	def tearDown(self):
		super().tearDown()
		cleanup_test_workspace(self.workspace, users=[self.owner], engine_tenant=self.tenant)

	def make_lead(self, name, email=None, status="New"):
		return frappe.get_doc({"doctype": "AI Lead", "tenant": self.tenant, "lead_name": name, "email": email, "source_channel": "Web", "status": status}).insert(ignore_permissions=True)

	def make_conversation(self, identifier):
		return frappe.get_doc({"doctype": "AI Chat Session", "tenant": self.tenant, "session_id": frappe.generate_hash(), "platform": "Web", "user_identifier": identifier, "status": "Open", "chat_history": "[]"}).insert(ignore_permissions=True)

	def test_lead_search_pagination_assignment_notes_status_and_funnel(self):
		first = self.make_lead("Alpha Buyer", "alpha@example.com")
		self.make_lead("Beta Buyer", "beta@example.com", "Won")
		frappe.set_user(self.owner)
		page = leads_api.list_leads(self.workspace, search="example.com", limit=1, start=0)
		self.assertTrue(page["success"])
		self.assertEqual(len(page["data"]["rows"]), 1)
		self.assertTrue(page["data"]["has_more"])
		self.assertEqual(page["data"]["funnel"]["counts"]["Won"], 1)
		self.assertTrue(leads_api.assign(self.workspace, first.name, self.owner, "Primary owner")["success"])
		self.assertTrue(leads_api.add_note(self.workspace, first.name, "Call tomorrow")["success"])
		self.assertTrue(leads_api.update_status(self.workspace, first.name, "Qualified", "Good fit")["success"])
		detail = leads_api.detail(self.workspace, first.name)["data"]
		self.assertEqual(detail["lead"]["status"], "Qualified")
		self.assertEqual({row.activity_type for row in detail["activities"]}, {"Assignment", "Note", "Status Change"})

	def test_lead_csv_export_neutralizes_formulas(self):
		self.make_lead("=HYPERLINK()", "safe@example.com")
		frappe.set_user(self.owner)
		leads_api.export_csv(self.workspace)
		content = frappe.local.response.filecontent.decode("utf-8-sig")
		self.assertIn("\t=HYPERLINK()", content)

	def test_conversation_handoff_assignment_resolution_and_export(self):
		conversation = self.make_conversation("visitor@example.com")
		frappe.set_user(self.owner)
		opened = conversations_api.update_handoff(self.workspace, conversation.name, "Open", note="Customer requested help")
		self.assertTrue(opened["success"])
		assigned = conversations_api.update_handoff(self.workspace, conversation.name, "Assigned", self.owner, "Taking over")
		self.assertEqual(assigned["data"]["assigned_to"], self.owner)
		resolved = conversations_api.update_handoff(self.workspace, conversation.name, "Resolved", self.owner, "Issue fixed")
		self.assertEqual(resolved["data"]["status"], "Resolved")
		self.assertEqual(len(resolved["data"]["history"]), 3)
		self.assertEqual(frappe.db.get_value("AI Chat Session", conversation.name, "status"), "Closed")
		page = conversations_api.list_conversations(self.workspace, search="visitor@example.com", limit=20)
		self.assertEqual(page["data"]["rows"][0]["handoff"]["status"], "Resolved")
		conversations_api.export_csv(self.workspace)
		self.assertIn("Resolved", frappe.local.response.filecontent.decode("utf-8-sig"))
