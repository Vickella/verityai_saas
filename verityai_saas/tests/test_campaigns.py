from datetime import date, timedelta

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils.file_manager import save_file
from verity_ai.engine.openai_handler import build_system_prompt

from verityai_saas import setup_doctypes
from verityai_saas.api import campaigns as campaigns_api
from verityai_saas.services import campaigns
from verityai_saas.services.onboarding import create_workspace
from verityai_saas.tests.cleanup import cleanup_all_test_fixtures, cleanup_test_workspace


class TestSalesCampaigns(FrappeTestCase):
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
		self.owner = self._user(f"campaign-owner-{token}@example.com")
		self.other_owner = self._user(f"campaign-other-{token}@example.com")
		self.created = create_workspace(self.owner, f"Campaign Account {token}", f"Campaign Workspace {token}")
		self.other = create_workspace(self.other_owner, f"Other Campaign {token}", f"Other Campaign Workspace {token}")
		self.workspace = self.created["workspace"]

	def tearDown(self):
		super().tearDown()
		cleanup_test_workspace(self.workspace, users=[self.owner], engine_tenant=self.created["engine_tenant"], commit=False)
		cleanup_test_workspace(self.other["workspace"], users=[self.other_owner], engine_tenant=self.other["engine_tenant"])

	def _user(self, email):
		return frappe.get_doc({"doctype": "User", "email": email, "first_name": "Campaign", "last_name": "Tester", "user_type": "Website User", "send_welcome_email": 0}).insert(ignore_permissions=True).name

	def _values(self, **updates):
		values = {
			"campaign_name": "Website launch offer", "campaign_code": "WEB-65", "channel": "Facebook",
			"objective": "Lead Generation", "headline": "Professional Website Development",
			"offer_summary": "A complete business website for $65, delivered in 48 hours.",
			"description": "Modern responsive design, full development, hosting, a domain and an AI assistant.",
			"target_audience": "Small businesses ready to get online", "offer_price": 65, "currency": "USD",
			"inclusions": "Modern design\nFull development\nFree domain and hosting for one year\nProfessional email",
			"terms": "Subject to scope confirmation.", "starts_on": str(date.today()),
			"ends_on": str(date.today() + timedelta(days=30)), "call_to_action": "Get started today",
			"destination_url": "https://www.veritycore.co.zw", "contact_phone": "0710 778 538",
			"response_guidance": "Answer questions using the exact offer and invite the lead to get started.",
		}
		values.update(updates)
		return values

	def test_crud_lifecycle_and_ai_grounding(self):
		doc = campaigns.create_campaign(self.workspace, self._values())
		self.assertEqual(doc["status"], "Draft")
		self.assertEqual(campaigns.list_campaigns(self.workspace)["counts"]["Draft"], 1)
		updated = campaigns.update_campaign(self.workspace, doc["name"], {"offer_price": 75, "offer_summary": "Updated complete website offer."})
		self.assertEqual(updated["offer_price"], 75)
		active = campaigns.set_status(self.workspace, doc["name"], "Active")
		self.assertTrue(active["is_current"])
		self.assertTrue(active["knowledge_source"])
		source = frappe.get_doc("AI Knowledge Source", active["knowledge_source"])
		self.assertEqual(source.tenant, self.created["engine_tenant"])
		self.assertEqual(source.active, 1)
		self.assertIn("Updated complete website offer", source.content)
		config = frappe.get_doc("AI Configuration", self.created["engine_configuration"])
		prompt = build_system_prompt(config, self.created["engine_tenant"], platform="Web", knowledge="")
		self.assertIn("Current approved sales campaigns", prompt)
		self.assertIn("USD 75", prompt)
		other_config = frappe.get_doc("AI Configuration", self.other["engine_configuration"])
		other_prompt = build_system_prompt(other_config, self.other["engine_tenant"], platform="Web", knowledge="")
		self.assertNotIn("Updated complete website offer", other_prompt)
		campaigns.set_status(self.workspace, doc["name"], "Paused")
		config.reload()
		prompt = build_system_prompt(config, self.created["engine_tenant"], platform="WhatsApp", knowledge="")
		self.assertNotIn("Current approved sales campaigns", prompt)
		self.assertEqual(frappe.db.get_value("AI Knowledge Source", source.name, "active"), 0)

	def test_workspace_boundary_blocks_detail_and_api_access(self):
		doc = campaigns.create_campaign(self.workspace, self._values())
		with self.assertRaises(frappe.DoesNotExistError):
			campaigns.campaign_detail(self.other["workspace"], doc["name"])
		frappe.set_user(self.other_owner)
		response = campaigns_api.detail(self.workspace, doc["name"])
		self.assertFalse(response["success"])
		self.assertEqual(response["code"], "WORKSPACE_FORBIDDEN")

	def test_dates_urls_codes_and_transitions_are_validated(self):
		with self.assertRaises(frappe.ValidationError):
			campaigns.create_campaign(self.workspace, self._values(starts_on="2026-09-20", ends_on="2026-09-19"))
		with self.assertRaises(frappe.ValidationError):
			campaigns.create_campaign(self.workspace, self._values(destination_url="javascript:alert(1)"))
		first = campaigns.create_campaign(self.workspace, self._values())
		with self.assertRaises(frappe.DuplicateEntryError):
			campaigns.create_campaign(self.workspace, self._values(campaign_name="Duplicate"))
		with self.assertRaises(frappe.ValidationError):
			campaigns.set_status(self.workspace, first["name"], "Completed")

	def test_future_and_expired_campaigns_do_not_ground_ai(self):
		future = campaigns.create_campaign(self.workspace, self._values(campaign_code="FUTURE", starts_on=str(date.today() + timedelta(days=1))))
		campaigns.set_status(self.workspace, future["name"], "Scheduled")
		self.assertEqual(campaigns.active_context(self.workspace)["active_count"], 0)
		with self.assertRaises(frappe.ValidationError):
			campaigns.set_status(self.workspace, future["name"], "Active")

	def test_private_image_metadata_is_saved_and_visible_to_ai(self):
		file_doc = save_file(f"{frappe.generate_hash(length=8)}-campaign.png", b"test image bytes", None, None, is_private=1)
		try:
			doc = campaigns.create_campaign(self.workspace, self._values(images=[{"image_file": file_doc.name, "alt_text": "Blue website development flyer", "caption": "Get started today", "visible_text": "All for $65; delivery in 48 hours"}]))
			detail = campaigns.campaign_detail(self.workspace, doc["name"])
			self.assertEqual(detail["images"][0]["image_file"], file_doc.name)
			self.assertIn("delivery in 48 hours", detail["ai_context"])
		finally:
			frappe.delete_doc("File", file_doc.name, ignore_permissions=True, force=True)

	def test_delete_requires_draft_or_archived(self):
		doc = campaigns.create_campaign(self.workspace, self._values())
		campaigns.set_status(self.workspace, doc["name"], "Active")
		with self.assertRaises(frappe.ValidationError):
			campaigns.delete_campaign(self.workspace, doc["name"])
		campaigns.set_status(self.workspace, doc["name"], "Paused")
		campaigns.set_status(self.workspace, doc["name"], "Archived")
		campaigns.delete_campaign(self.workspace, doc["name"])
		self.assertFalse(frappe.db.exists("VerityAI Sales Campaign", doc["name"]))

	def test_managed_campaign_knowledge_is_protected_and_self_healing(self):
		from verityai_saas.services import engine

		doc = campaigns.create_campaign(self.workspace, self._values())
		active = campaigns.set_status(self.workspace, doc["name"], "Active")
		source = active["knowledge_source"]
		with self.assertRaises(frappe.ValidationError):
			engine.update_knowledge_source(self.workspace, source, {"content": "Unapproved replacement"})
		with self.assertRaises(frappe.ValidationError):
			engine.delete_knowledge_source(self.workspace, source)
		frappe.delete_doc("AI Knowledge Source", source, ignore_permissions=True, force=True)
		campaigns.sync_workspace_context(self.workspace)
		recreated = frappe.db.get_value("VerityAI Sales Campaign", doc["name"], "knowledge_source")
		self.assertTrue(recreated)
		self.assertNotEqual(recreated, source)
		self.assertTrue(frappe.db.exists("AI Knowledge Source", recreated))

	def test_campaign_portal_contains_complete_crud_and_image_flow(self):
		from pathlib import Path

		root = Path(__file__).resolve().parents[1]
		portal = (root / "public" / "js" / "portal.js").read_text(encoding="utf-8")
		template = (root / "templates" / "pages" / "customer_portal.html").read_text(encoding="utf-8")
		for marker in ("async function campaigns()", "campaign-image-picker", "data-campaign-edit", "data-campaign-delete", "verityai_saas.api.campaigns.set_status", "AI grounding preview"):
			self.assertIn(marker, portal)
		self.assertIn('("campaigns", "Campaigns")', template)
