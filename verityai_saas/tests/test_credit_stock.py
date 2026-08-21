from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from verityai_saas.services import credit_stock
from verityai_saas.setup_doctypes import ensure_doctypes


class TestCreditStockLedger(FrappeTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		ensure_doctypes()
		frappe.db.delete("VerityAI Credit Stock Ledger", {"source_key": ["like", "test-credit-stock:%"]})

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.delete("VerityAI Credit Stock Ledger", {"source_key": ["like", "test-credit-stock:%"]})

	def test_weighted_cost_and_profit_are_recorded(self):
		with patch("verityai_saas.services.credit_stock._last_entry", side_effect=[None, None, None]):
			opening = credit_stock.record_entry("Opening Balance", 1000, 10, source_key="test-credit-stock:opening")
		with patch("verityai_saas.services.credit_stock._last_entry", return_value=opening):
			allocation = credit_stock.record_entry("Allocation", 200, 5, "Issue", source_key="test-credit-stock:allocation")
		self.assertEqual(int(opening.balance_credits), 1000)
		self.assertEqual(int(allocation.balance_credits), 800)
		self.assertAlmostEqual(float(allocation.cogs), 2.0, places=2)
		self.assertAlmostEqual(float(allocation.gross_profit), 3.0, places=2)

	def test_source_key_makes_allocation_idempotent(self):
		first = credit_stock.record_entry("Purchase", 500, 4, source_key="test-credit-stock:purchase")
		second = credit_stock.record_entry("Purchase", 500, 4, source_key="test-credit-stock:purchase")
		self.assertEqual(first.name, second.name)

	@patch("verityai_saas.services.credit_stock._request")
	def test_erpnext_post_is_idempotent(self, request):
		entry = credit_stock.record_entry("Allocation", 10, 2, "Issue", source_key="test-credit-stock:post")
		settings = frappe.get_single("VerityAI ERPNext Accounting Settings")
		settings.update({
			"enabled": 1, "erpnext_url": "https://erp.example.com", "api_key": "key", "api_secret": "secret",
			"company": "Example", "receivable_account": "Bank - EX", "sales_account": "Sales - EX",
			"inventory_account": "AI Credits - EX", "cogs_account": "Cost of AI Credits - EX", "cost_center": "Main - EX",
		})
		settings.save(ignore_permissions=True)
		request.side_effect = [{"data": []}, {"data": {"name": "ACC-JV-0001", "docstatus": 0}}, {"data": {"name": "ACC-JV-0001", "docstatus": 1}}]
		result = credit_stock.post_to_erpnext(entry.name)
		self.assertEqual(result["journal_entry"], "ACC-JV-0001")
		again = credit_stock.post_to_erpnext(entry.name)
		self.assertTrue(again["already_posted"])
		self.assertEqual(request.call_count, 3)
