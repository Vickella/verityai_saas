from unittest.mock import Mock, patch

import frappe
from frappe.tests.utils import FrappeTestCase

from verityai_saas import setup_doctypes
from verityai_saas.tests.cleanup import cleanup_all_test_fixtures, cleanup_test_workspace
from verityai_saas.services import billing, engine, notifications, onboarding, usage, whatsapp
from verityai_saas.services.admin_reauth import mark_admin_reauthenticated
from verityai_saas.services.permissions import check_workspace_access, require_operator


class TestVerityAISaaS(FrappeTestCase):
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
		mark_admin_reauthenticated()
		token = frappe.generate_hash(length=8).lower()
		self.owner = self.create_user(f"owner-{token}@example.com")
		self.other = self.create_user(f"other-{token}@example.com")
		self.created = onboarding.create_workspace(self.owner, f"Account {token}", f"Workspace {token}", f"Business {token}")
		self.workspace = self.created["workspace"]
		self.tenant = self.created["engine_tenant"]

	def tearDown(self):
		super().tearDown()
		cleanup_test_workspace(self.workspace, users=[self.owner, self.other], engine_tenant=self.tenant)

	def create_user(self, email):
		return frappe.get_doc({"doctype": "User", "email": email, "first_name": "SaaS", "last_name": "Tester", "user_type": "Website User", "send_welcome_email": 0}).insert(ignore_permissions=True).name

	def enable_full_whatsapp_for_test(self):
		plan = frappe.db.get_value("VerityAI Subscription", self.created["subscription"], "plan")
		frappe.db.set_value("VerityAI Plan", plan, "can_use_whatsapp_ai", 1)

	def test_onboarding_creates_complete_core_graph(self):
		self.assertTrue(frappe.db.exists("VerityAI Account", self.created["account"]))
		self.assertTrue(frappe.db.exists("VerityAI Workspace Member", self.created["member"]))
		self.assertTrue(frappe.db.exists("AI Tenant", self.tenant))
		self.assertEqual(frappe.db.get_value("AI Configuration", self.created["engine_configuration"], "tenant"), self.tenant)
		self.assertTrue(frappe.db.exists("VerityAI Subscription", self.created["subscription"]))
		self.assertTrue(frappe.db.exists("VerityAI Usage Wallet", self.created["wallet"]))
		self.assertEqual(frappe.db.count("VerityAI Onboarding Checklist", {"workspace": self.workspace}), len(onboarding.CHECKLIST))

	def test_setup_cannot_finish_before_required_steps(self):
		with self.assertRaises(frappe.ValidationError):
			onboarding.complete_setup(self.workspace, user=self.owner)

	def test_post_launch_steps_are_skipped_when_setup_finishes(self):
		for code in onboarding.REQUIRED_SETUP_STEPS:
			onboarding.set_step(self.workspace, code, "Done", user=self.owner)
		result = onboarding.complete_setup(self.workspace, user=self.owner)
		self.assertEqual(result["setup_progress"], 100)
		self.assertEqual(frappe.db.get_value("VerityAI Workspace", self.workspace, "onboarding_status"), "Complete")
		statuses = dict(frappe.get_all("VerityAI Onboarding Checklist", filters={"workspace": self.workspace}, fields=["step_code", "status"], as_list=True))
		self.assertTrue(all(statuses[code] == "Skipped" for code in onboarding.POST_LAUNCH_STEPS))

	def test_cross_workspace_access_is_rejected(self):
		frappe.set_user(self.other)
		with self.assertRaises(frappe.PermissionError):
			check_workspace_access(self.workspace)

	def test_owner_can_access_own_workspace(self):
		frappe.set_user(self.owner)
		self.assertEqual(check_workspace_access(self.workspace).name, self.workspace)

	def test_assistant_and_widget_only_update_linked_tenant(self):
		other_tenant = frappe.get_doc({"doctype": "AI Tenant", "tenant_name": f"other-{frappe.generate_hash(length=8)}", "assistant_name": "Other", "active": 1}).insert(ignore_permissions=True)
		engine.update_assistant_identity(self.workspace, {"assistant_name": "My Assistant", "system_prompt": "must not write"})
		engine.update_widget_settings(self.workspace, {"widget_title": "Help", "provider_api_key": "must not write"})
		self.assertEqual(frappe.db.get_value("AI Tenant", self.tenant, "assistant_name"), "My Assistant")
		self.assertEqual(frappe.db.get_value("AI Tenant", self.tenant, "widget_title"), "Help")
		engine.update_widget_settings(self.workspace, {"widget_primary_color": "#2f6fed", "widget_header_color": "#16345f"})
		colours = frappe.db.get_value("AI Tenant", self.tenant, ["widget_primary_color", "widget_header_color"], as_dict=True)
		self.assertEqual(colours.widget_primary_color, "#2f6fed")
		self.assertEqual(colours.widget_header_color, "#16345f")
		self.assertIn("widget.js?v=20260817-2", engine.generate_embed_code(self.workspace))
		with self.assertRaises(frappe.ValidationError):
			engine.update_widget_settings(self.workspace, {"widget_primary_color": "url(javascript:alert(1))"})
		self.assertEqual(frappe.db.get_value("AI Tenant", other_tenant.name, "assistant_name"), "Other")

	def test_assistant_uses_curated_business_nature(self):
		settings = engine.safe_settings(self.workspace)
		self.assertIn("Consultancy", {row.business_nature for row in settings["business_natures"]})
		updated = engine.update_assistant_identity(self.workspace, {"business_nature": "Consultancy"})
		self.assertEqual(updated["business_nature"], "Consultancy")
		self.assertEqual(frappe.db.get_value("VerityAI Workspace", self.workspace, "business_nature"), "Consultancy")
		with self.assertRaises(frappe.ValidationError):
			engine.update_assistant_identity(self.workspace, {"business_nature": "Made Up Industry"})

	def test_allowed_domains_are_normalized_and_scoped(self):
		self.assertEqual(engine.replace_allowed_domains(self.workspace, ["https://www.Example.com/path"]), ["example.com"])
		self.assertEqual(frappe.get_all("AI Allowed Domain", filters={"parent": self.tenant}, pluck="domain"), ["example.com"])

	def test_knowledge_leads_conversations_and_usage_are_tenant_scoped(self):
		source = engine.create_knowledge_source(self.workspace, "FAQ", "We open Monday to Friday.")
		self.assertEqual(frappe.db.get_value("AI Knowledge Source", source, "tenant"), self.tenant)
		session = frappe.get_doc({"doctype": "AI Chat Session", "session_id": frappe.generate_hash(), "tenant": self.tenant, "platform": "Web", "status": "Open", "chat_history": "[]"}).insert(ignore_permissions=True)
		lead = frappe.get_doc({"doctype": "AI Lead", "lead_name": "Scoped Lead", "tenant": self.tenant, "chat_session": session.name, "status": "New"}).insert(ignore_permissions=True)
		log = frappe.get_doc({"doctype": "AI Usage Log", "tenant": self.tenant, "chat_session": session.name, "platform": "Web", "input_tokens": 10, "output_tokens": 5, "total_tokens": 15, "status": "Success"}).insert(ignore_permissions=True)
		self.assertEqual(engine.get_workspace_leads(self.workspace)[0].name, lead.name)
		self.assertEqual(engine.get_workspace_conversations(self.workspace)[0].name, session.name)
		self.assertEqual(engine.get_workspace_usage(self.workspace)["total_tokens"], 15)
		usage.sync_workspace_usage(self.workspace)
		self.assertTrue(frappe.db.exists("VerityAI Usage Transaction", {"ai_usage_log": log.name, "workspace": self.workspace}))

	def test_plan_limits_and_suspension_update_engine(self):
		plan = frappe.get_doc("VerityAI Plan", "TRIAL")
		plan.monthly_token_limit = 12345
		plan.save(ignore_permissions=True)
		engine.apply_plan_limits(self.workspace, plan.name)
		self.assertEqual(frappe.db.get_value("AI Configuration", {"tenant": self.tenant}, "monthly_token_limit"), 12345)
		billing.set_subscription_status(self.workspace, "Suspended", "Test")
		self.assertEqual(frappe.db.get_value("AI Tenant", self.tenant, "active"), 0)

	def test_trial_reduction_preserves_non_trial_credits(self):
		from verityai_saas.services.billing import apply_trial_allowance_limit

		frappe.db.set_value(
			"VerityAI Usage Wallet",
			self.created["wallet"],
			{"opening_token_allowance": 50_000, "top_up_tokens": 2_000, "promotional_credits": 1_000, "tokens_used": 4_000},
		)
		self.assertEqual(apply_trial_allowance_limit(10_000, self.workspace), 1)
		wallet = frappe.db.get_value(
			"VerityAI Usage Wallet",
			self.created["wallet"],
			["opening_token_allowance", "top_up_tokens", "promotional_credits", "tokens_remaining"],
			as_dict=True,
		)
		self.assertEqual(wallet.opening_token_allowance, 10_000)
		self.assertEqual(wallet.top_up_tokens, 2_000)
		self.assertEqual(wallet.promotional_credits, 1_000)
		self.assertEqual(wallet.tokens_remaining, 9_000)

	def test_email_delivery_log_is_created(self):
		with patch("frappe.sendmail"):
			logs = notifications.send_notification(self.workspace, "Test", "Subject", "Body")
		self.assertTrue(logs)
		self.assertEqual(frappe.db.get_value("VerityAI Email Delivery Log", logs[0], "status"), "Sent")

	def test_whatsapp_secrets_are_write_only(self):
		self.enable_full_whatsapp_for_test()
		data = whatsapp.configure(self.workspace, {"mode": "Full AI Automation", "whatsapp_phone_id": "phone-id", "whatsapp_access_token": "access-secret", "meta_verify_token": "verify-secret", "meta_app_secret": "app-secret", "verify_meta_signature": 1})
		serialized = frappe.as_json(data)
		self.assertNotIn("access-secret", serialized)
		self.assertNotIn("app-secret", serialized)
		self.assertNotIn("verify-secret", serialized)
		self.assertTrue(data["engine"]["access_token_present"])

	def test_customer_cannot_use_operator_dashboard(self):
		frappe.set_user(self.owner)
		with self.assertRaises(frappe.PermissionError):
			require_operator()

	def test_operator_can_use_operator_dashboard(self):
		frappe.set_user("Administrator")
		self.assertEqual(require_operator(), "Administrator")


	def test_whatsapp_connection_test_and_webhook_activity_are_safe(self):
		self.enable_full_whatsapp_for_test()
		whatsapp.configure(self.workspace, {
			"mode": "Full AI Automation", "whatsapp_phone_id": "phone-id",
			"whatsapp_access_token": "access-secret", "meta_verify_token": "verify-secret",
			"meta_app_secret": "app-secret", "verify_meta_signature": 1,
		})
		response = Mock(ok=True, content=b"{}", reason="OK")
		response.json.return_value = {
			"id": "phone-id", "display_phone_number": "+263700000000",
			"verified_name": "Verity Test", "quality_rating": "GREEN",
		}
		with patch("requests.get", return_value=response) as graph_get:
			result = whatsapp.test_connection(self.workspace)
		self.assertTrue(result["connected"])
		self.assertNotIn("access-secret", frappe.as_json(result))
		self.assertEqual(graph_get.call_args.kwargs["timeout"], 20)
		whatsapp.record_channel_activity(frappe._dict({
			"platform": "WhatsApp", "tenant": self.tenant, "name": "wa-session-test",
		}))
		setup = whatsapp.safe_setup(self.workspace)
		self.assertEqual(setup["webhook_health"]["status"], "Healthy")
		self.assertEqual(setup["last_webhook_event"], "wa-session-test")
