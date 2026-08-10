import json
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from verityai_saas.install import REQUIRED_ENGINE_DOCTYPES, validate_engine_installation
from verityai_saas.setup_doctypes import ensure_workspace


class TestStandaloneInstallation(FrappeTestCase):
	def test_platform_settings_are_admin_only(self):
		permissions = {row.role for row in frappe.get_meta("VerityAI Platform Settings").permissions if row.read}
		self.assertEqual(permissions, {"System Manager", "VerityAI SaaS Administrator"})

	@staticmethod
	def links_by_card(workspace):
		links = {}
		card = None
		for row in workspace.links:
			if row.type == "Card Break":
				card = row.label
				links.setdefault(card, [])
			elif card:
				links[card].append(row.link_to)
		return links

	def test_commerce_card_extends_engine_workspace_idempotently(self):
		ensure_workspace()
		ensure_workspace()
		workspace = frappe.get_doc("Workspace", "Verity AI")
		self.assertTrue(workspace.hide_custom)
		cards = [row.get("data", {}).get("card_name") for row in json.loads(workspace.content)]
		self.assertEqual(cards.count("Commerce"), 1)
		links = self.links_by_card(workspace)
		self.assertNotIn("AI Configuration", {target for targets in links.values() for target in targets})
		commerce_links = set(links["Commerce"])
		self.assertEqual(
			commerce_links,
			{"VerityAI Customer", "VerityAI Product", "VerityAI Product Price", "VerityAI Quotation"},
		)
		sales_links = set(links["Sales"])
		self.assertTrue(
			{"VerityAI Sales Opportunity", "VerityAI Appointment", "VerityAI CRM Activity"}.issubset(sales_links)
		)

	def test_engine_dependency_is_validated_locally(self):
		self.assertTrue(validate_engine_installation())

	@patch("verityai_saas.install.frappe.db.exists", return_value=False)
	def test_missing_engine_has_clear_local_error(self, _exists):
		with self.assertRaises(frappe.ValidationError) as error:
			validate_engine_installation()
		for doctype in REQUIRED_ENGINE_DOCTYPES:
			self.assertIn(doctype, str(error.exception))
