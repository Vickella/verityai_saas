import json
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase
from verity_ai.engine.tools import get_lead_capture_schema

from verityai_saas.install import REQUIRED_ENGINE_DOCTYPES, validate_engine_installation
from verityai_saas.services.business_natures import BUSINESS_NATURES, seed_business_natures
from verityai_saas.setup_doctypes import ensure_default_plan, ensure_workspace


class TestStandaloneInstallation(FrappeTestCase):
	def test_public_plans_and_credit_packs_match_commercial_baseline(self):
		ensure_default_plan()
		expected = {
			"TRIAL": (0, 10_000), "LAUNCH": (12, 500_000), "GROWTH": (24, 1_500_000),
			"SCALE": (60, 6_000_000), "ENTERPRISE": (100, 12_000_000),
		}
		for code, (price, credits) in expected.items():
			plan = frappe.db.get_value("VerityAI Plan", {"plan_code": code}, ["monthly_price", "monthly_token_limit", "active"], as_dict=True)
			self.assertIsNotNone(plan)
			self.assertEqual(float(plan.monthly_price), price)
			self.assertEqual(plan.monthly_token_limit, credits)
			self.assertEqual(bool(plan.active), code != "ENTERPRISE")
		self.assertEqual(frappe.db.count("VerityAI Credit Pack", {"active": 1}), 3)

	def test_business_natures_are_comprehensive_and_idempotent(self):
		seed_business_natures()
		seed_business_natures()
		self.assertGreaterEqual(len(BUSINESS_NATURES), 16)
		self.assertTrue(frappe.db.exists("AI Business Nature", "Consultancy"))
		consultancy = frappe.get_doc("AI Business Nature", "Consultancy")
		fields = {row.fieldname: row for row in consultancy.lead_fields}
		self.assertTrue({"advisory_area", "current_challenge", "desired_outcome", "decision_makers"}.issubset(fields))
		self.assertTrue(fields["current_challenge"].required)
		self.assertEqual(len(fields), len(set(fields)))

	def test_engine_reads_seeded_sales_discovery_schema(self):
		seed_business_natures()
		name = f"schema-{frappe.generate_hash(length=8).lower()}"
		frappe.get_doc(
			{
				"doctype": "AI Tenant",
				"tenant_name": name,
				"business_nature": "Consultancy",
				"active": 1,
			}
		).insert(ignore_permissions=True)
		try:
			schema = json.loads(get_lead_capture_schema(name))
			self.assertTrue(schema["success"])
			self.assertEqual(schema["business_nature"], "Consultancy")
			self.assertIn("current_challenge", {field["fieldname"] for field in schema["fields"]})
		finally:
			frappe.delete_doc("AI Tenant", name, ignore_permissions=True, force=True)

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
