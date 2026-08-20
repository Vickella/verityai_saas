from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from verityai_saas import setup_doctypes
from verityai_saas.services import commerce, erpnext, onboarding
from verityai_saas.tests.cleanup import cleanup_all_test_fixtures, cleanup_test_workspace


PUBLIC_DNS = [(2, 1, 6, "", ("93.184.216.34", 443))]


class TestRemoteERPNext(FrappeTestCase):
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
		self.owner = frappe.get_doc({"doctype": "User", "email": f"erp-owner-{token}@example.com", "first_name": "ERP", "user_type": "Website User", "send_welcome_email": 0}).insert(ignore_permissions=True).name
		self.created = onboarding.create_workspace(self.owner, f"ERP Account {token}", f"ERP Workspace {token}")
		self.workspace = self.created["workspace"]
		self.plan = frappe.db.get_value("VerityAI Subscription", self.created["subscription"], "plan")
		self.original_erpnext_entitlement = frappe.db.get_value("VerityAI Plan", self.plan, "can_use_erpnext_integration")
		frappe.db.set_value("VerityAI Plan", self.plan, "can_use_erpnext_integration", 1)

	def tearDown(self):
		super().tearDown()
		frappe.db.set_value("VerityAI Plan", self.plan, "can_use_erpnext_integration", self.original_erpnext_entitlement)
		cleanup_test_workspace(self.workspace, users=[self.owner], engine_tenant=self.created["engine_tenant"])

	@patch("verityai_saas.services.erpnext.socket.getaddrinfo", return_value=PUBLIC_DNS)
	def _configure(self, _dns, **values):
		return erpnext.configure(self.workspace, {"enabled": 1, "url": "https://erp.example.com", "api_key": "key", "api_secret": "secret", **values})

	def test_connection_can_require_installed_connector(self):
		self._configure(assistant_connector_enabled=1)
		with patch("verityai_saas.services.erpnext._request") as request:
			request.side_effect = [
				{"message": "integration@example.com"}, {"data": [{"name": "Example Co"}]},
				{"message": {"connector": True, "arbitrary_script_execution": False}},
			]
			result = erpnext.test_connection(self.workspace)
		self.assertTrue(result["connector"]["connector"])
		self.assertFalse(result["connector"]["arbitrary_script_execution"])

	def test_product_sync_is_idempotent_and_workspace_scoped(self):
		self._configure()
		items = [{"name": "ITEM-1", "item_code": "ITEM-1", "item_name": "ERP product", "stock_uom": "Unit", "is_stock_item": 1, "disabled": 0}]
		prices = [{"item_code": "ITEM-1", "price_list": "Standard Selling", "currency": "USD", "price_list_rate": 42}]
		with patch("verityai_saas.services.erpnext._resource_rows", side_effect=[items, prices, items, prices]):
			first = erpnext.sync_products(self.workspace)
			second = erpnext.sync_products(self.workspace)
		self.assertEqual(first["created"], 1)
		self.assertEqual(second["updated"], 1)
		product = frappe.db.get_value("VerityAI Product", {"workspace": self.workspace, "item_code": "ITEM-1"}, ["standard_rate", "external_system"], as_dict=True)
		self.assertEqual(product.standard_rate, 42)
		self.assertEqual(product.external_system, "ERPNext")

	def test_approved_quote_syncs_once(self):
		self._configure(auto_sync_quotations=1)
		customer = commerce.save_customer(self.workspace, {"customer_name": "Buyer"})
		product = commerce.save_product(self.workspace, {"item_code": "SERVICE", "item_name": "Service", "standard_rate": 100})
		quotation = commerce.save_quotation(self.workspace, {"customer": customer.name, "items": [{"product": product.name, "qty": 2}]})
		commerce.set_quotation_status(self.workspace, quotation.name, "Pending Approval")
		with patch("verityai_saas.services.erpnext._resource_rows", return_value=[]), patch("verityai_saas.services.erpnext._request") as request:
			request.side_effect = [{"data": {"name": "ERP-CUST-1"}}, {"data": {"name": "SAL-QTN-0001"}}]
			commerce.set_quotation_status(self.workspace, quotation.name, "Approved")
			result = erpnext.sync_quotation(self.workspace, quotation.name)
		self.assertTrue(result["already_synced"])
		self.assertEqual(frappe.db.get_value("VerityAI Quotation", quotation.name, "external_id"), "SAL-QTN-0001")

	@patch("verityai_saas.services.erpnext.socket.getaddrinfo", return_value=[(2, 1, 6, "", ("127.0.0.1", 443))])
	def test_private_network_targets_are_rejected(self, _dns):
		with self.assertRaises(frappe.ValidationError):
			erpnext.configure(self.workspace, {"enabled": 1, "url": "https://internal.example", "api_key": "key", "api_secret": "secret"})
