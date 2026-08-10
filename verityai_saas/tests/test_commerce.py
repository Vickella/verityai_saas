import json
from types import SimpleNamespace
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from verityai_saas import setup_doctypes
from verityai_saas.api import commerce as commerce_api
from verityai_saas.services import commerce
from verityai_saas.services.onboarding import create_workspace
from verityai_saas.tests.cleanup import cleanup_all_test_fixtures, cleanup_test_workspace


class TestTenantNativeCommerce(FrappeTestCase):
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
		self.owner = self.create_user(f"commerce-owner-{token}@example.com")
		self.other_owner = self.create_user(f"commerce-other-{token}@example.com")
		self.created = create_workspace(self.owner, f"Commerce Account {token}", f"Commerce Workspace {token}")
		self.other = create_workspace(self.other_owner, f"Other Commerce {token}", f"Other Commerce Workspace {token}")
		self.workspace = self.created["workspace"]
		self.customer = commerce.save_customer(self.workspace, {"customer_name": "Acme", "email": "buyer@example.com"})
		self.product = commerce.save_product(self.workspace, {"item_code": "CONSULT", "item_name": "Consulting", "standard_rate": 100, "currency": "USD"})

	def tearDown(self):
		super().tearDown()
		cleanup_test_workspace(self.workspace, users=[self.owner], engine_tenant=self.created["engine_tenant"], commit=False)
		cleanup_test_workspace(self.other["workspace"], users=[self.other_owner], engine_tenant=self.other["engine_tenant"])

	def create_user(self, email):
		return frappe.get_doc({"doctype": "User", "email": email, "first_name": "Commerce", "last_name": "Tester", "user_type": "Website User", "send_welcome_email": 0}).insert(ignore_permissions=True).name

	def create_lead(self, workspace=None, name="CRM Lead"):
		created = self.created if not workspace or workspace == self.workspace else self.other
		return frappe.get_doc({"doctype": "AI Lead", "tenant": created["engine_tenant"], "lead_name": name, "email": f"{frappe.generate_hash(length=8)}@example.com", "phone": "+263700000000", "source_channel": "Web", "status": "New", "requirements": "Needs a proposal"}).insert(ignore_permissions=True)

	def test_customer_and_item_codes_are_unique_only_inside_workspace(self):
		other_customer = commerce.save_customer(self.other["workspace"], {"customer_name": "Acme", "email": "other@example.com"})
		other_product = commerce.save_product(self.other["workspace"], {"item_code": "CONSULT", "item_name": "Other Consulting", "standard_rate": 999})
		self.assertNotEqual(other_customer.name, self.customer.name)
		self.assertNotEqual(other_product.name, self.product.name)
		with self.assertRaises(frappe.DuplicateEntryError):
			commerce.save_product(self.workspace, {"item_code": "consult", "item_name": "Duplicate"})

	def test_workspace_price_and_quote_totals_are_calculated_server_side(self):
		price = commerce.save_price(self.workspace, {"product": self.product.name, "price_list": "Retail", "currency": "USD", "rate": 120})
		quote = commerce.save_quotation(self.workspace, {
			"customer": self.customer.name, "transaction_date": "2026-08-10", "valid_till": "2026-08-31",
			"price_list": "Retail", "currency": "USD", "discount_amount": 16, "tax_rate": 15,
			"items": [{"product": self.product.name, "qty": 2, "discount_percent": 10}],
		})
		self.assertEqual(price.rate, 120)
		self.assertEqual(quote["items"][0]["rate"], 120)
		self.assertEqual(quote["items"][0]["amount"], 216)
		self.assertEqual(quote.subtotal, 216)
		self.assertEqual(quote.tax_amount, 30)
		self.assertEqual(quote.total, 230)
		self.assertFalse(quote.external_id)

	def test_cross_workspace_references_and_customer_api_access_are_blocked(self):
		other_product = commerce.save_product(self.other["workspace"], {"item_code": "PRIVATE", "item_name": "Private Product", "standard_rate": 50})
		with self.assertRaises(frappe.DoesNotExistError):
			commerce.save_quotation(self.workspace, {"customer": self.customer.name, "items": [{"product": other_product.name, "qty": 1}]})
		frappe.set_user(self.owner)
		response = commerce_api.products(self.other["workspace"])
		self.assertFalse(response["success"])
		self.assertEqual(response["code"], "WORKSPACE_FORBIDDEN")
		own = commerce_api.products(self.workspace)
		self.assertTrue(own["success"])
		self.assertEqual([row.name for row in own["data"]], [self.product.name])

	def test_quote_workflow_is_controlled_and_non_drafts_are_immutable(self):
		quote = commerce.save_quotation(self.workspace, {"customer": self.customer.name, "items": [{"product": self.product.name, "qty": 1}]})
		commerce.set_quotation_status(self.workspace, quote.name, "Pending Approval")
		with self.assertRaises(frappe.ValidationError):
			commerce.set_quotation_status(self.workspace, quote.name, "Sent")
		commerce.set_quotation_status(self.workspace, quote.name, "Approved")
		with self.assertRaises(frappe.ValidationError):
			commerce.save_quotation(self.workspace, {"customer": self.customer.name, "items": [{"product": self.product.name, "qty": 2}]}, quotation=quote.name)

	def test_referenced_customer_and_product_cannot_be_deleted(self):
		commerce.save_quotation(self.workspace, {"customer": self.customer.name, "items": [{"product": self.product.name, "qty": 1}]})
		with self.assertRaises(frappe.ValidationError):
			commerce.delete_customer(self.workspace, self.customer.name)
		with self.assertRaises(frappe.ValidationError):
			commerce.delete_product(self.workspace, self.product.name)

	def test_pdf_download_is_scoped(self):
		quote = commerce.save_quotation(self.workspace, {"customer": self.customer.name, "items": [{"product": self.product.name, "qty": 1}], "notes": "Thank you"})
		frappe.set_user(self.owner)
		with patch("frappe.utils.pdf.get_pdf", return_value=b"%PDF-commerce"):
			commerce_api.download_quotation(self.workspace, quote.name)
		self.assertEqual(frappe.local.response.filecontent, b"%PDF-commerce")
		self.assertEqual(frappe.local.response.type, "pdf")

	def test_ai_quote_tools_use_native_commerce_unless_erpnext_is_enabled(self):
		from verity_ai.engine import tools as ai_tools
		from verity_ai.engine.openai_handler import get_tool_definitions

		config = frappe.get_doc("AI Configuration", {"tenant": self.created["engine_tenant"]})
		web_tools = {row["function"]["name"] for row in get_tool_definitions(config, platform="Web")}
		desk_tools = {row["function"]["name"] for row in get_tool_definitions(config, platform="Desk")}
		self.assertTrue({"search_product_catalog", "get_item_price", "request_quotation_approval", "check_quote_status"}.issubset(web_tools))
		self.assertIn("manage_native_sales", desk_tools)
		catalogue = json.loads(ai_tools.search_product_catalog(config, "consult"))
		self.assertEqual(catalogue["products"][0]["item_code"], "CONSULT")
		price = commerce.handle_ai_item_price(self.created["engine_tenant"], "consult")
		self.assertTrue(price["handled"])
		self.assertEqual(price["public_selling_price"], 100)
		engine_price = json.loads(ai_tools.get_item_price(
			frappe.get_doc("AI Configuration", {"tenant": self.created["engine_tenant"]}), "CONSULT"
		))
		self.assertEqual(engine_price["public_selling_price"], 100)
		created = commerce.handle_ai_quotation_request(
			self.created["engine_tenant"], "AI Buyer", [{"item_code": "CONSULT", "qty": 2}],
			client_email="ai-buyer@example.com",
		)
		self.assertTrue(created["handled"])
		self.assertEqual(created["estimated_total"], 200)
		status = commerce.handle_ai_quote_status(
			self.created["engine_tenant"], created["quotation"], client_email="ai-buyer@example.com"
		)
		self.assertTrue(status["success"])
		self.assertEqual(status["quotation_status"], "Pending Approval")
		engine_created = json.loads(ai_tools.request_quotation_approval(
			frappe.get_doc("AI Configuration", {"tenant": self.created["engine_tenant"]}),
			"Engine Buyer", [{"item_code": "CONSULT", "qty": 1}],
			tenant_name=self.created["engine_tenant"], client_email="engine-buyer@example.com",
		))
		self.assertTrue(engine_created["success"])
		self.assertEqual(engine_created["estimated_total"], 100)
		frappe.db.set_value("AI Configuration", config.name, "enable_erpnext_integration", 1)
		self.assertIsNone(commerce.handle_ai_item_price(self.created["engine_tenant"], "CONSULT"))

	def test_ai_lead_appointments_and_desk_crm_are_mapped_to_native_sales(self):
		from verity_ai.engine import tools as ai_tools
		from verity_ai.engine.openai_handler import execute_tool_call_impl

		result = json.loads(ai_tools.capture_lead(
			self.created["engine_tenant"], None, "Scheduled Buyer",
			email="scheduled@example.com", appointment_requested=True,
			appointment_date="2026-08-25", appointment_time="14:00",
			appointment_mode="Online", appointment_notes="Product demonstration",
		))
		self.assertTrue(result["success"])
		self.assertIsNone(result["customer"])
		self.assertTrue(result["appointment"])
		self.assertEqual(frappe.db.get_value("VerityAI Appointment", result["appointment"], "workspace"), self.workspace)
		self.assertTrue(frappe.db.exists("VerityAI CRM Activity", {"workspace": self.workspace, "lead": result["lead_id"]}))

		pipeline = json.loads(ai_tools.manage_native_sales(
			self.created["engine_tenant"], self.owner, "pipeline_summary"
		))
		self.assertTrue(pipeline["success"])
		self.assertIn("counts", pipeline["data"])
		tool_call = SimpleNamespace(function=SimpleNamespace(
			name="manage_native_sales", arguments=json.dumps({"action": "list_appointments"})
		))
		dispatched = json.loads(execute_tool_call_impl(
			tool_call,
			frappe.get_doc("AI Configuration", {"tenant": self.created["engine_tenant"]}),
			self.created["engine_tenant"], SimpleNamespace(name=None), self.owner, platform="Desk",
		))
		self.assertTrue(dispatched["success"])
		self.assertEqual(dispatched["data"][0]["name"], result["appointment"])
		forbidden = json.loads(ai_tools.manage_native_sales(
			self.created["engine_tenant"], self.other_owner, "pipeline_summary"
		))
		self.assertFalse(forbidden["success"])

	def test_lead_conversion_creates_scoped_customer_and_opportunity(self):
		lead = self.create_lead()
		result = commerce.convert_lead(self.workspace, lead.name, {"amount": 500, "expected_close_date": "2026-09-30"})
		self.assertEqual(result["lead"], lead.name)
		self.assertEqual(frappe.db.get_value("VerityAI Customer", result["customer"], "workspace"), self.workspace)
		self.assertEqual(frappe.db.get_value("VerityAI Customer", result["customer"], "source_lead"), lead.name)
		self.assertEqual(frappe.db.get_value("VerityAI Sales Opportunity", result["opportunity"], "stage"), "Qualified")
		self.assertEqual(frappe.db.get_value("AI Lead", lead.name, "status"), "Qualified")
		repeated = commerce.convert_lead(self.workspace, lead.name, {"amount": 999})
		self.assertTrue(repeated["already_converted"])
		self.assertEqual(repeated["opportunity"], result["opportunity"])
		other_lead = self.create_lead(self.other["workspace"], "Other CRM Lead")
		with self.assertRaises(frappe.DoesNotExistError):
			commerce.convert_lead(self.workspace, other_lead.name)

	def test_pipeline_conversion_and_won_value_are_workspace_scoped(self):
		opportunity = commerce.save_opportunity(self.workspace, {"opportunity_name": "Expansion", "customer": self.customer.name, "stage": "New", "amount": 750, "probability": 10})
		for stage in ("Qualified", "Proposal", "Negotiation", "Won"):
			opportunity = commerce.set_opportunity_stage(self.workspace, opportunity.name, stage)
		pipeline = commerce.list_opportunities(self.workspace)
		self.assertEqual(pipeline["counts"]["Won"], 1)
		self.assertEqual(pipeline["won_value"], 750)
		self.assertEqual(frappe.db.get_value("VerityAI Customer", self.customer.name, "lifetime_value"), 750)
		self.assertEqual(commerce.list_opportunities(self.other["workspace"])["won_value"], 0)

	def test_appointments_and_activity_history_validate_workspace_links(self):
		opportunity = commerce.save_opportunity(self.workspace, {"opportunity_name": "Meeting Deal", "customer": self.customer.name, "amount": 200})
		appointment = commerce.save_appointment(self.workspace, {"subject": "Discovery call", "customer": self.customer.name, "opportunity": opportunity.name, "starts_on": "2026-08-20 10:00:00", "ends_on": "2026-08-20 10:30:00", "mode": "Online"})
		commerce.set_appointment_status(self.workspace, appointment.name, "Completed", "Requirements confirmed")
		activity = commerce.save_activity(self.workspace, {"activity_type": "Meeting", "subject": "Discovery completed", "customer": self.customer.name, "opportunity": opportunity.name, "appointment": appointment.name, "status": "Completed"})
		self.assertEqual(activity.status, "Completed")
		self.assertTrue(frappe.db.get_value("VerityAI Customer", self.customer.name, "last_contact_on"))
		self.assertTrue(frappe.db.get_value("VerityAI Sales Opportunity", opportunity.name, "last_contact_on"))
		follow_up = commerce.save_activity(self.workspace, {"activity_type": "Follow-up", "subject": "Send proposal", "customer": self.customer.name, "status": "Open"})
		completed = commerce.set_activity_status(self.workspace, follow_up.name, "Completed")
		self.assertEqual(completed.status, "Completed")
		other_customer = commerce.save_customer(self.other["workspace"], {"customer_name": "Other Appointment Customer"})
		with self.assertRaises(frappe.DoesNotExistError):
			commerce.save_appointment(self.workspace, {"subject": "Leak", "customer": other_customer.name, "starts_on": "2026-08-20 12:00:00"})
