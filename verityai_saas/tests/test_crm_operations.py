import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_to_date, now_datetime
from types import SimpleNamespace
from unittest.mock import patch

from verityai_saas import setup_doctypes
from verityai_saas.api import conversations as conversations_api
from verityai_saas.api import leads as leads_api
from verityai_saas.services import followups, whatsapp
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

	def make_conversation(self, identifier, platform="Web"):
		return frappe.get_doc({"doctype": "AI Chat Session", "tenant": self.tenant, "session_id": frappe.generate_hash(), "platform": platform, "user_identifier": identifier, "last_customer_message_on": now_datetime() if platform == "WhatsApp" else None, "status": "Open", "chat_history": frappe.as_json([{"role": "system", "content": "private system prompt"}, {"role": "user", "content": "We need manufacturing stock visibility"}, {"role": "assistant", "content": "I can help capture that requirement."}, {"role": "assistant", "content": "  "}, {"role": "tool", "content": "private tool payload"}])}).insert(ignore_permissions=True)

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

	def test_lead_detail_returns_ai_needs_and_scoped_conversation(self):
		conversation = self.make_conversation("buyer@example.com")
		lead = frappe.get_doc({
			"doctype": "AI Lead", "tenant": self.tenant, "lead_name": "Manufacturing Buyer",
			"email": "buyer@example.com", "source_channel": "Web", "status": "New",
			"current_system": "Odoo", "problems_faced": "Stock movement detail is limited",
			"requirements": "Manufacturing, budgets and three users",
			"dynamic_details": frappe.as_json({"number_of_users": 3, "modules": "All modules"}),
			"chat_session": conversation.name,
		}).insert(ignore_permissions=True)
		frappe.set_user(self.owner)
		response = leads_api.detail(self.workspace, lead.name)
		self.assertTrue(response["success"])
		data = response["data"]
		self.assertEqual(data["lead"]["current_system"], "Odoo")
		self.assertEqual(data["lead"]["requirements"], "Manufacturing, budgets and three users")
		self.assertEqual([row["role"] for row in data["conversation"]["history"]], ["user", "assistant"])
		self.assertNotIn("private tool payload", frappe.as_json(data))
		denied = leads_api.detail("missing-workspace", lead.name)
		self.assertFalse(denied["success"])
		self.assertEqual(denied["code"], "NOT_FOUND")

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

	def test_conversation_detail_exposes_only_public_nonempty_messages(self):
		conversation = self.make_conversation("visitor@example.com")
		frappe.set_user(self.owner)
		data = conversations_api.detail(self.workspace, conversation.name)["data"]
		self.assertEqual([item["role"] for item in data["history"]], ["user", "assistant"])
		self.assertNotIn("private system prompt", frappe.as_json(data))
		self.assertNotIn("private tool payload", frappe.as_json(data))

	def test_whatsapp_reply_and_scheduled_follow_up(self):
		conversation = self.make_conversation("263776552106", platform="WhatsApp")
		frappe.db.set_value("AI Configuration", {"tenant": self.tenant}, "whatsapp_phone_id", "123456")
		frappe.db.set_value("AI Chat Session", conversation.name, {"channel_account": "removed-account", "channel_phone_number_id": "stale-phone-id"})
		frappe.set_user(self.owner)
		with patch("verityai_saas.services.followups.send_whatsapp_message_result", return_value={"accepted": True, "message_id": "wamid.manual", "status": "accepted", "error": None}) as sender:
			response = conversations_api.send_reply(self.workspace, conversation.name, "Are you ready to continue?")
			self.assertTrue(response["data"]["sent"])
			sender.assert_called_once()
			self.assertEqual(sender.call_args.args[0], "123456")
		history = frappe.parse_json(frappe.db.get_value("AI Chat Session", conversation.name, "chat_history"))
		self.assertEqual(history[-1]["content"], "Are you ready to continue?")
		self.assertEqual(history[-1]["delivery_status"], "Accepted")
		self.assertEqual(frappe.db.get_value("VerityAI WhatsApp Message", {"meta_message_id": "wamid.manual"}, "status"), "Accepted")
		due_at = add_to_date(now_datetime(), hours=1)
		scheduled = conversations_api.schedule_follow_up(self.workspace, conversation.name, "I can help you complete the next step.", due_at)
		follow_up = scheduled["data"]["follow_up"]
		self.assertEqual(frappe.db.get_value("VerityAI Conversation Follow Up", follow_up, "status"), "Scheduled")
		cancelled = conversations_api.cancel_follow_up(self.workspace, follow_up)
		self.assertEqual(cancelled["data"]["cancelled"], follow_up)

	def test_start_whatsapp_conversation_uses_inbound_session_key(self):
		frappe.db.set_value("AI Configuration", {"tenant": self.tenant}, "whatsapp_phone_id", "123456")
		frappe.set_user(self.owner)
		created = conversations_api.start_whatsapp_conversation(self.workspace, "+263 77 655 2106")
		self.assertTrue(created["success"])
		conversation = frappe.get_doc("AI Chat Session", created["data"]["conversation"])
		self.assertEqual(conversation.session_id, "wa_263776552106")
		self.assertEqual(conversation.user_identifier, "263776552106")
		self.assertEqual(conversation.platform, "WhatsApp")
		# Calling it again returns the same thread that the inbound webhook uses.
		reopened = conversations_api.start_whatsapp_conversation(self.workspace, "263776552106")
		self.assertEqual(reopened["data"]["conversation"], conversation.name)

	def test_legacy_whatsapp_duplicates_merge_and_old_links_redirect(self):
		phone = "263771112233"
		frappe.db.set_value("AI Configuration", {"tenant": self.tenant}, "whatsapp_phone_id", "123456")
		first = frappe.get_doc({
			"doctype": "AI Chat Session", "tenant": self.tenant, "session_id": f"wa_old_one_{phone}",
			"platform": "WhatsApp", "user_identifier": phone, "status": "Open",
			"chat_history": frappe.as_json([{"role": "user", "content": "Can you help with a website?"}]),
		}).insert(ignore_permissions=True)
		second = frappe.get_doc({
			"doctype": "AI Chat Session", "tenant": self.tenant, "session_id": f"wa_old_two_{phone}",
			"platform": "WhatsApp", "user_identifier": f"+{phone}", "status": "Open",
			"chat_history": frappe.as_json([{"role": "assistant", "content": "Yes, our team can help."}]),
		}).insert(ignore_permissions=True)
		frappe.set_user(self.owner)
		result = conversations_api.start_whatsapp_conversation(self.workspace, phone)
		self.assertTrue(result["success"], result)
		primary_name = result["data"]["conversation"]
		self.assertIn(primary_name, {first.name, second.name})
		duplicate_name = second.name if primary_name == first.name else first.name
		self.assertEqual(frappe.db.get_value("AI Chat Session", duplicate_name, "merged_into"), primary_name)
		rows = conversations_api.list_conversations(self.workspace, platform="WhatsApp", search=phone)["data"]["rows"]
		self.assertEqual([row["name"] for row in rows], [primary_name])
		detail = conversations_api.detail(self.workspace, duplicate_name)["data"]
		self.assertEqual(detail["name"], primary_name)
		self.assertEqual([item["content"] for item in detail["history"]], ["Can you help with a website?", "Yes, our team can help."])

	def test_conversation_list_has_safe_message_preview(self):
		conversation = self.make_conversation("preview@example.com")
		frappe.set_user(self.owner)
		row = conversations_api.list_conversations(self.workspace, search="preview@example.com")["data"]["rows"][0]
		self.assertEqual(row["last_message"], "I can help capture that requirement.")
		self.assertEqual(row["last_role"], "assistant")
		self.assertNotIn("chat_history", row)
		self.assertNotIn("private tool payload", frappe.as_json(row))

	def test_web_visitors_receive_stable_numbered_labels(self):
		first = self.make_conversation("")
		second = self.make_conversation("")
		frappe.set_user(self.owner)
		rows = conversations_api.list_conversations(self.workspace, platform="Web")["data"]["rows"]
		labels = {row["name"]: row["display_name"] for row in rows}
		self.assertEqual(labels[first.name], "WEB v1")
		self.assertEqual(labels[second.name], "WEB v2")
		self.assertEqual(conversations_api.detail(self.workspace, second.name)["data"]["display_name"], "WEB v2")

	def test_due_follow_up_uses_the_conversations_whatsapp_account(self):
		conversation = self.make_conversation("263771234567", platform="WhatsApp")
		setup_name = frappe.db.get_value("VerityAI WhatsApp Setup", {"workspace": self.workspace}, "name")
		setup = frappe.get_doc("VerityAI WhatsApp Setup", setup_name)
		setup.whatsapp_phone_id = "phone-account-1"
		setup.whatsapp_access_token = "test-token"
		setup.is_default = 1
		setup.save(ignore_permissions=True)
		conversation.channel_account = setup.name
		conversation.channel_phone_number_id = setup.whatsapp_phone_id
		conversation.save(ignore_permissions=True)
		follow_up = frappe.get_doc({
			"doctype": "VerityAI Conversation Follow Up", "workspace": self.workspace,
			"conversation": conversation.name, "due_at": now_datetime(), "recipient": conversation.user_identifier,
			"message": "Checking whether you would like to continue.", "status": "Scheduled",
		}).insert(ignore_permissions=True)
		with patch("verityai_saas.services.followups.send_whatsapp_message_result", return_value={"accepted": True, "message_id": "wamid.followup", "status": "accepted", "error": None}) as sender:
			followups.process_due_followups()
			self.assertEqual(sender.call_args.args[0], "phone-account-1")
			self.assertEqual(sender.call_args.kwargs["config"].name, setup.name)
		self.assertEqual(frappe.db.get_value(follow_up.doctype, follow_up.name, "status"), "Sent")

	def test_meta_delivery_receipts_update_message_and_conversation(self):
		conversation = self.make_conversation("263771234568", platform="WhatsApp")
		frappe.db.set_value("AI Configuration", {"tenant": self.tenant}, "whatsapp_phone_id", "phone-receipts")
		frappe.set_user(self.owner)
		with patch("verityai_saas.services.followups.send_whatsapp_message_result", return_value={"accepted": True, "message_id": "wamid.receipt", "status": "accepted", "error": None}):
			self.assertTrue(conversations_api.send_reply(self.workspace, conversation.name, "Delivery tracked message")["data"]["sent"])
		followups.record_delivery_status(self.tenant, phone_number_id="phone-receipts", message_id="wamid.receipt", recipient=conversation.user_identifier, status="delivered")
		self.assertEqual(frappe.db.get_value("VerityAI WhatsApp Message", {"meta_message_id": "wamid.receipt"}, "status"), "Delivered")
		detail = conversations_api.detail(self.workspace, conversation.name)["data"]
		self.assertEqual(detail["history"][-1]["delivery_status"], "Delivered")
		followups.record_delivery_status(self.tenant, phone_number_id="phone-receipts", message_id="wamid.receipt", recipient=conversation.user_identifier, status="read")
		self.assertEqual(frappe.db.get_value("VerityAI WhatsApp Message", {"meta_message_id": "wamid.receipt"}, "status"), "Read")

	def test_rejected_message_is_not_added_to_conversation(self):
		conversation = self.make_conversation("263771234569", platform="WhatsApp")
		frappe.db.set_value("AI Configuration", {"tenant": self.tenant}, "whatsapp_phone_id", "phone-rejected")
		before = frappe.parse_json(conversation.chat_history)
		frappe.set_user(self.owner)
		with patch("verityai_saas.services.followups.send_whatsapp_message_result", return_value={"accepted": False, "message_id": None, "status": "failed", "error": "Meta rejected this recipient"}):
			result = conversations_api.send_reply(self.workspace, conversation.name, "This must not appear")["data"]
		self.assertFalse(result["sent"])
		self.assertEqual(frappe.parse_json(frappe.db.get_value("AI Chat Session", conversation.name, "chat_history")), before)
		self.assertEqual(frappe.db.get_value("VerityAI WhatsApp Message", result["delivery_log"], "status"), "Failed")

	def test_legacy_conversation_recovers_recent_customer_window_from_inbound_usage(self):
		conversation = self.make_conversation("263771234574", platform="WhatsApp")
		conversation.last_customer_message_on = None
		conversation.save(ignore_permissions=True)
		frappe.db.set_value("AI Configuration", {"tenant": self.tenant}, "whatsapp_phone_id", "phone-recovered-window")
		frappe.get_doc({
			"doctype": "AI Usage Log", "tenant": self.tenant, "chat_session": conversation.name,
			"platform": "WhatsApp", "status": "Success", "operation": "assistant_response",
			"source_feature": "whatsapp_ai", "total_tokens": 1,
		}).insert(ignore_permissions=True)
		frappe.set_user(self.owner)
		with patch("verityai_saas.services.followups.send_whatsapp_message_result", return_value={"accepted": True, "message_id": "wamid.recovered", "status": "accepted", "error": None}) as sender, patch("verityai_saas.services.followups.send_whatsapp_template_result") as template_sender:
			result = conversations_api.send_reply(self.workspace, conversation.name, "A custom follow-up inside the recovered window")["data"]
		self.assertTrue(result["sent"])
		sender.assert_called_once()
		template_sender.assert_not_called()
		self.assertIsNotNone(frappe.db.get_value("AI Chat Session", conversation.name, "last_customer_message_on"))

	def test_transport_exception_returns_retryable_failure_and_closes_sending_log(self):
		conversation = self.make_conversation("263771234573", platform="WhatsApp")
		frappe.db.set_value("AI Configuration", {"tenant": self.tenant}, "whatsapp_phone_id", "phone-exception")
		before = frappe.parse_json(conversation.chat_history)
		frappe.set_user(self.owner)
		with patch("verityai_saas.services.followups.send_whatsapp_message_result", side_effect=RuntimeError("temporary provider failure")):
			result = conversations_api.send_reply(self.workspace, conversation.name, "Please retry this message")["data"]
		self.assertFalse(result["sent"])
		self.assertEqual(result["status"], "Failed")
		self.assertIn("temporary provider failure", result["error"])
		self.assertEqual(frappe.db.get_value("VerityAI WhatsApp Message", result["delivery_log"], "status"), "Failed")
		self.assertEqual(frappe.parse_json(frappe.db.get_value("AI Chat Session", conversation.name, "chat_history")), before)

	def test_stale_conversation_uses_verified_template_and_preserves_edited_message(self):
		conversation = self.make_conversation("263771234570", platform="WhatsApp")
		conversation.last_customer_message_on = add_to_date(now_datetime(), days=-2)
		conversation.save(ignore_permissions=True)
		setup = frappe.get_doc("VerityAI WhatsApp Setup", frappe.db.get_value("VerityAI WhatsApp Setup", {"workspace": self.workspace}, "name"))
		setup.whatsapp_phone_id = "phone-template"
		setup.whatsapp_access_token = "test-token"
		setup.reengagement_template_name = "sales_follow_up"
		setup.reengagement_template_language = "en_US"
		setup.reengagement_template_status = "Approved"
		setup.save(ignore_permissions=True)
		conversation.channel_account = setup.name
		conversation.channel_phone_number_id = setup.whatsapp_phone_id
		conversation.save(ignore_permissions=True)
		frappe.set_user(self.owner)
		message = "Would you like me to send the onboarding form for your manufacturing team?"
		with patch("verityai_saas.services.followups.send_whatsapp_template_result", return_value={"accepted": True, "message_id": "wamid.template", "status": "accepted", "error": None, "delivery_method": "Template", "template_name": "sales_follow_up"}) as template_sender, patch("verityai_saas.services.followups.send_whatsapp_message_result") as text_sender:
			result = conversations_api.send_reply(self.workspace, conversation.name, message)["data"]
		self.assertTrue(result["sent"])
		self.assertEqual(result["delivery_method"], "Template")
		template_sender.assert_called_once()
		self.assertEqual(template_sender.call_args.args, ("phone-template", conversation.user_identifier, message, "sales_follow_up", "en_US"))
		self.assertEqual(template_sender.call_args.kwargs["config"].name, setup.name)
		text_sender.assert_not_called()
		self.assertEqual(frappe.db.get_value("VerityAI WhatsApp Message", result["delivery_log"], "message"), message)

	def test_stale_conversation_never_attempts_invalid_free_form_delivery(self):
		conversation = self.make_conversation("263771234571", platform="WhatsApp")
		conversation.last_customer_message_on = add_to_date(now_datetime(), days=-2)
		conversation.save(ignore_permissions=True)
		setup = frappe.get_doc("VerityAI WhatsApp Setup", frappe.db.get_value("VerityAI WhatsApp Setup", {"workspace": self.workspace}, "name"))
		setup.whatsapp_phone_id = "phone-no-template"
		setup.reengagement_template_name = None
		setup.reengagement_template_status = "Not Configured"
		setup.save(ignore_permissions=True)
		conversation.channel_account = setup.name
		conversation.channel_phone_number_id = setup.whatsapp_phone_id
		conversation.save(ignore_permissions=True)
		frappe.set_user(self.owner)
		with patch("verityai_saas.services.followups.send_whatsapp_message_result") as text_sender, patch("verityai_saas.services.followups.send_whatsapp_template_result") as template_sender:
			result = conversations_api.send_reply(self.workspace, conversation.name, "Can we continue with your website setup?")["data"]
		self.assertFalse(result["sent"])
		self.assertIn("approved WhatsApp follow-up template", result["error"])
		text_sender.assert_not_called()
		template_sender.assert_not_called()

	@patch("requests.get")
	def test_follow_up_template_verification_requires_approved_single_body_variable(self, get):
		setup = frappe.get_doc("VerityAI WhatsApp Setup", frappe.db.get_value("VerityAI WhatsApp Setup", {"workspace": self.workspace}, "name"))
		setup.whatsapp_access_token = "test-token"
		setup.meta_waba_id = "waba-one"
		setup.reengagement_template_name = "sales_follow_up"
		setup.reengagement_template_language = "en_US"
		setup.save(ignore_permissions=True)
		get.return_value.content = b"payload"
		get.return_value.ok = True
		get.return_value.json.return_value = {"data": [{"name": "sales_follow_up", "language": "en_US", "status": "APPROVED", "components": [{"type": "BODY", "text": "Following up on our conversation: {{1}}"}]}]}
		result = whatsapp.verify_reengagement_template(self.workspace, setup.name)
		self.assertTrue(result["approved"])
		self.assertEqual(frappe.db.get_value(setup.doctype, setup.name, "reengagement_template_status"), "Approved")

	def test_conversation_ui_has_mobile_single_thread_and_desktop_composer_controls(self):
		with open(frappe.get_app_path("verityai_saas", "public", "js", "portal.js"), encoding="utf-8") as source:
			javascript = source.read()
		with open(frappe.get_app_path("verityai_saas", "public", "css", "portal.css"), encoding="utf-8") as source:
			stylesheet = source.read()
		for marker in ("mobile-chat-open", "va-chat-back", "send-whatsapp-reply", "wa-reply-form", "wa-send-status", "conversationSendPending", "retry_follow_up", "Sync messages", "Verify follow-up template", 'maxlength="1000"', "preserveScrollTop", "wasAtBottom", "chatRenderSequence"):
			self.assertIn(marker, javascript)
		for marker in (".va-chat-app.mobile-chat-open", ".va-chat-layout.chat-open .va-chat-sidebar", "overflow-y: auto", "grid-template-rows: auto minmax(0,1fr) auto"):
			self.assertIn(marker, stylesheet)

	def test_generic_follow_up_copy_is_rejected_before_operator_review(self):
		self.assertTrue(followups._generic_follow_up("Just checking in. Let me know how I can assist."))
		self.assertFalse(followups._generic_follow_up("Would you like me to send the onboarding form for your logistics website now?"))

	def test_ai_draft_repairs_generic_copy_with_conversation_context(self):
		conversation = self.make_conversation("263771234572", platform="WhatsApp")
		generic = SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="Just checking in. Let me know how I can assist."))])
		contextual = SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="Would you like me to arrange the manufacturing stock-visibility demo this week?"))])
		with patch("verityai_saas.services.followups.get_config", return_value={"model_name": "test-model"}), patch("verityai_saas.services.followups.assert_usage_within_limit"), patch("verityai_saas.services.followups.get_client", return_value=object()), patch("verityai_saas.services.followups.create_chat_completion", side_effect=[generic, contextual]) as completion, patch("verityai_saas.services.followups.extract_usage", return_value={}), patch("verityai_saas.services.followups.log_usage"):
			result = followups.draft(self.workspace, conversation.name)
		self.assertEqual(result["message"], "Would you like me to arrange the manufacturing stock-visibility demo this week?")
		self.assertEqual(completion.call_count, 2)
		self.assertIn("generic", completion.call_args.args[3][-1]["content"])
