import frappe
from frappe.tests.utils import FrappeTestCase

from verity_ai.api import connector


class TestERPNextConnector(FrappeTestCase):
	def test_guest_cannot_access_connector(self):
		frappe.set_user("Guest")
		with self.assertRaises(frappe.PermissionError):
			connector.health()

	def test_system_manager_receives_safe_capabilities(self):
		frappe.set_user("Administrator")
		result = connector.health()
		self.assertTrue(result["connector"])
		self.assertFalse(result["arbitrary_script_execution"])
		self.assertIn("reports_and_exports", result["capabilities"])
