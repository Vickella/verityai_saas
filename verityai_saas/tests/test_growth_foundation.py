import json

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, now_datetime

from verityai_saas.api import growth as growth_api
from verityai_saas.services import growth, whatsapp
from verityai_saas.services.onboarding import create_workspace
from verityai_saas.setup_doctypes import ensure_doctypes
from verityai_saas.tests.cleanup import cleanup_test_workspace


class TestGrowthFoundation(FrappeTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		ensure_doctypes()
		growth.seed_default_channels()
		self.token = frappe.generate_hash(length=8).upper()
		self.channel_code = f"TEST_{self.token}"
		self.campaign_code = f"CAMPAIGN_{self.token}"
		self.source = f"test-growth-{self.token.lower()}"
		self.original_flags = growth.feature_flags()

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.delete("VerityAI Growth Event", {"source": self.source})
		frappe.db.delete("VerityAI Consent Record", {"source": self.source})
		frappe.db.delete("VerityAI Suppression Record", {"source": self.source})
		frappe.db.delete("VerityAI Growth Campaign", {"campaign_code": self.campaign_code})
		frappe.db.delete("VerityAI Growth Channel", {"channel_code": self.channel_code})
		growth.configure_feature_flags(self.original_flags)

	def create_channel(self):
		return growth.save_channel({
			"channel_name": "Test governed channel",
			"channel_code": self.channel_code,
			"channel_type": "Owned",
			"delivery_mode": "Human Approved",
			"risk_class": "Moderate",
			"status": "Active",
			"monthly_limit": 25,
		})

	def test_default_channel_catalog_is_idempotent(self):
		growth.seed_default_channels()
		growth.seed_default_channels()
		codes = set(frappe.get_all("VerityAI Growth Channel", pluck="channel_code"))
		self.assertTrue({row[0] for row in growth.DEFAULT_CHANNELS}.issubset(codes))

	def test_feature_releases_are_independent(self):
		updated = growth.configure_feature_flags({
			"growth_foundation_enabled": 1,
			"website_doctor_internal_enabled": 1,
			"public_audits_enabled": 1,
			"website_builder_enabled": 0,
			"partner_portal_enabled": 0,
			"white_label_enabled": 0,
			"outbound_enabled": 0,
		})
		self.assertTrue(updated["growth_foundation_enabled"])
		self.assertTrue(updated["website_doctor_internal_enabled"])
		self.assertTrue(updated["public_audits_enabled"])
		self.assertFalse(updated["website_builder_enabled"])
		self.assertFalse(updated["outbound_enabled"])

	def test_public_call_cannot_change_release_controls(self):
		frappe.set_user("Guest")
		response = growth_api.configure_feature_flags({"public_audits_enabled": 1})
		self.assertFalse(response["success"])
		self.assertEqual(response["code"], "AUTH_REQUIRED")
		frappe.set_user("Administrator")
		self.assertEqual(growth.feature_flags(), self.original_flags)

	def test_channel_and_campaign_validation(self):
		channel = self.create_channel()
		self.assertEqual(channel["channel_code"], self.channel_code)
		self.assertEqual(channel["monthly_limit"], 25)
		campaign = growth.save_campaign({
			"campaign_name": "Current product proof",
			"campaign_code": self.campaign_code,
			"channel": channel["name"],
			"objective": "Activation",
			"status": "Draft",
			"source": "website",
			"medium": "owned",
			"starts_on": "2026-09-03",
			"ends_on": "2026-09-30",
		})
		self.assertEqual(campaign["channel"], channel["name"])
		with self.assertRaises(frappe.ValidationError):
			growth.save_campaign({
				"campaign_name": "Invalid window",
				"campaign_code": f"BAD_{self.token}",
				"channel": channel["name"],
				"objective": "Acquisition",
				"starts_on": "2026-09-30",
				"ends_on": "2026-09-03",
			})

	def test_events_are_idempotent_and_immutable(self):
		channel = self.create_channel()
		key = f"growth-event-{self.token.lower()}"
		first = growth.record_event(
			"widget.lead_captured",
			channel=channel["name"],
			source=self.source,
			idempotency_key=key,
			metadata={"variant": "proof"},
		)
		second = growth.record_event(
			"widget.lead_captured",
			channel=channel["name"],
			source=self.source,
			idempotency_key=key,
			metadata={"variant": "ignored-duplicate"},
		)
		self.assertEqual(first.name, second.name)
		self.assertEqual(json.loads(first.metadata), {"variant": "proof"})
		first.source = "changed"
		with self.assertRaises(frappe.PermissionError):
			first.save(ignore_permissions=True)
		with self.assertRaises(frappe.PermissionError):
			frappe.delete_doc("VerityAI Growth Event", first.name, ignore_permissions=True)

	def test_consent_and_suppression_store_only_keyed_hashes(self):
		channel = self.create_channel()
		identifier = f"Person-{self.token}@Example.com"
		consent = growth.record_consent(
			identifier,
			"Lead",
			"Product education",
			channel=channel["name"],
			source=self.source,
			evidence="Explicit website checkbox",
		)
		self.assertNotEqual(consent.subject_hash, identifier.casefold())
		self.assertNotIn(identifier.casefold(), consent.subject_hash)

		suppression = growth.suppress(
			identifier,
			"Customer opted out",
			channel=channel["name"],
			source=self.source,
		)
		duplicate = growth.suppress(
			identifier,
			"Duplicate opt-out",
			channel=channel["name"],
			source=self.source,
		)
		self.assertEqual(suppression.name, duplicate.name)
		self.assertTrue(growth.is_suppressed(identifier, channel["name"]))
		self.assertFalse(growth.is_suppressed(identifier, "WHATSAPP"))
		growth.lift_suppression(suppression.name)
		self.assertFalse(growth.is_suppressed(identifier, channel["name"]))

	def test_expired_suppression_is_not_counted_or_reused(self):
		channel = self.create_channel()
		identifier = f"expired-{self.token}@example.com"
		old = growth.suppress(
			identifier,
			"Temporary pause",
			channel=channel["name"],
			expires_on=add_days(now_datetime(), -1),
			source=self.source,
		)
		self.assertFalse(growth.is_suppressed(identifier, channel["name"]))
		new = growth.suppress(
			identifier,
			"New request",
			channel=channel["name"],
			source=self.source,
		)
		self.assertNotEqual(old.name, new.name)
		self.assertEqual(frappe.db.get_value("VerityAI Suppression Record", old.name, "status"), "Expired")

	def test_operator_ui_contains_growth_controls(self):
		with open(frappe.get_app_path("verityai_saas", "public", "js", "admin.js"), encoding="utf-8") as handle:
			script = handle.read()
		with open(frappe.get_app_path("verityai_saas", "public", "css", "portal.css"), encoding="utf-8") as handle:
			stylesheet = handle.read()
		self.assertIn('["growth","Growth"]', script)
		self.assertIn("One transparent growth control plane", script)
		self.assertIn("growth-consent-form", script)
		self.assertIn("growth-suppression-form", script)
		self.assertIn("Product conversion funnel", script)
		self.assertIn("Website project foundation", script)
		self.assertIn("Website Doctor operations", script)
		self.assertIn("website-audit-pilot-form", script)
		self.assertIn("website-doctor-configuration-form", script)
		self.assertIn("Website Doctor CRM workspace", script)
		self.assertIn(".va-inline-action", stylesheet)
		self.assertIn(".va-growth-hero", stylesheet)

	def test_product_channels_share_conversation_to_crm_attribution(self):
		growth.configure_feature_flags({"growth_foundation_enabled": 1})
		owner = frappe.get_doc({
			"doctype": "User",
			"email": f"growth-owner-{self.token.lower()}@example.com",
			"first_name": "Growth",
			"last_name": "Tester",
			"user_type": "Website User",
			"send_welcome_email": 0,
		}).insert(ignore_permissions=True).name
		created = create_workspace(owner, f"Growth Account {self.token}", f"Growth Workspace {self.token}")
		workspace = created["workspace"]
		try:
			conversation = frappe.get_doc({
				"doctype": "AI Chat Session", "session_id": frappe.generate_hash(),
				"tenant": created["engine_tenant"], "platform": "Web",
				"user_identifier": "private-visitor@example.com", "status": "Open", "chat_history": "[]",
			}).insert(ignore_permissions=True)
			lead = frappe.get_doc({
				"doctype": "AI Lead", "tenant": created["engine_tenant"], "lead_name": "Private Buyer",
				"email": "private-buyer@example.com", "phone": "+263700000000",
				"chat_session": conversation.name, "source_channel": "Web", "status": "New",
				"dynamic_details": json.dumps({"attribution": {"source": "website", "medium": "widget"}}),
			}).insert(ignore_permissions=True)
			opportunity = frappe.get_doc({
				"doctype": "VerityAI Sales Opportunity", "workspace": workspace,
				"opportunity_name": "Growth opportunity", "lead": lead.name,
				"stage": "New", "amount": 125, "currency": "USD",
			}).insert(ignore_permissions=True)
			lead.status = "Qualified"
			lead.save(ignore_permissions=True)
			opportunity.stage = "Won"
			opportunity.save(ignore_permissions=True)

			events = frappe.get_all("VerityAI Growth Event", filters={"workspace": workspace}, fields=["event_type", "channel", "correlation_id", "metadata"])
			self.assertEqual(
				{row.event_type for row in events},
				{"conversation.started", "lead.captured", "lead.qualified", "opportunity.created", "opportunity.won"},
			)
			self.assertTrue(all(row.channel == "WIDGET" for row in events))
			self.assertTrue(all(row.correlation_id == conversation.name for row in events))
			self.assertNotIn("private-buyer@example.com", json.dumps(events))
			widget = next(row for row in growth.channel_funnel() if row["channel_code"] == "WIDGET")
			self.assertGreaterEqual(widget["conversations"], 1)
			self.assertGreaterEqual(widget["leads"], 1)
			self.assertGreaterEqual(widget["won"], 1)
			self.assertGreaterEqual(widget["won_value"], 125)

			whatsapp_conversation = frappe.get_doc({
				"doctype": "AI Chat Session", "session_id": frappe.generate_hash(),
				"tenant": created["engine_tenant"], "platform": "WhatsApp",
				"user_identifier": "+263711111111", "status": "Open", "chat_history": "[]",
			}).insert(ignore_permissions=True)
			frappe.get_doc({
				"doctype": "AI Lead", "tenant": created["engine_tenant"], "lead_name": "WhatsApp Buyer",
				"phone": "+263711111111", "chat_session": whatsapp_conversation.name,
				"source_channel": "WhatsApp", "status": "New",
			}).insert(ignore_permissions=True)
			setup = frappe.db.get_value("VerityAI WhatsApp Setup", {"workspace": workspace}, "name")
			frappe.db.set_value("VerityAI WhatsApp Setup", setup, "meta_waba_id", "test-waba")
			whatsapp.record_inbound_webhook(
				created["engine_tenant"], message_id=f"message-{self.token}",
				from_number="+263711111111", message="private message body",
			)
			whatsapp.record_inbound_webhook(created["engine_tenant"], message_id=f"message-{self.token}")
			whatsapp_events = frappe.get_all(
				"VerityAI Growth Event", filters={"workspace": workspace, "channel": "WHATSAPP"},
				fields=["event_type", "metadata", "correlation_id"],
			)
			self.assertEqual(sum(row.event_type == "channel.inbound_received" for row in whatsapp_events), 1)
			self.assertTrue({"conversation.started", "lead.captured", "channel.inbound_received"}.issubset({row.event_type for row in whatsapp_events}))
			serialized = json.dumps(whatsapp_events)
			self.assertNotIn("+263711111111", serialized)
			self.assertNotIn("private message body", serialized)
			whatsapp_funnel = next(row for row in growth.channel_funnel() if row["channel_code"] == "WHATSAPP")
			self.assertGreaterEqual(whatsapp_funnel["inbound_messages"], 1)
			self.assertGreaterEqual(whatsapp_funnel["conversations"], 1)
			self.assertGreaterEqual(whatsapp_funnel["leads"], 1)
		finally:
			cleanup_test_workspace(workspace, users=[owner], engine_tenant=created["engine_tenant"])
