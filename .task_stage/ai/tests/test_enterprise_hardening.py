import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from verity_ai.action_registry import action_risk
from verity_ai.api.chat import assert_public_rate_limit, header_background, primary_colours, validate_public_message
from verity_ai.api.control_room import decide_action_approval, decide_quote_request, summary as control_room_summary, update_alert_status
from verity_ai.api.cors import tenant_allows_origin
from verity_ai.api.setup_wizard import status as setup_wizard_status, validate_domains
from verity_ai.engine import tools
from verity_ai.api.whatsapp import get_config_for_phone, is_duplicate_event
from verity_ai.engine.openai_handler import UsageLimitExceeded, execute_tool_call, get_or_create_session, get_tool_definitions, process_chat
from verity_ai.knowledge_index import chunk_text, content_hash, embed_knowledge_chunks, rebuild_knowledge_chunks, search_knowledge_chunks
from verity_ai.monitoring import alert_notification_due, create_or_update_alert, get_monitoring_summary, monitor_pending_approvals, monitor_token_usage, record_whatsapp_failure
from verity_ai.retention import cleanup_chat_sessions, cleanup_doctype
from verity_ai.sales.quotation_flow import public_quote_status
from verity_ai.setup_doctypes import create_doctypes, optional_doctype_link


class TestEnterpriseHardening(FrappeTestCase):
	@patch("verity_ai.setup_doctypes.frappe.db.exists", return_value=False)
	def test_optional_erpnext_links_degrade_to_data_on_frappe_only_sites(self, _exists):
		field = optional_doctype_link("customer", "Customer", "Customer", read_only=1)
		self.assertEqual(field["fieldtype"], "Data")
		self.assertIsNone(field["options"])
		self.assertEqual(field["read_only"], 1)

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		create_doctypes()

	def setUp(self):
		self.tenant_name = f"Test Tenant {frappe.generate_hash(length=8)}"
		self.tenant = frappe.get_doc(
			{
				"doctype": "AI Tenant",
				"tenant_name": self.tenant_name,
				"active": 1,
			}
		).insert(ignore_permissions=True)
		self.config = frappe.get_doc(
			{
				"doctype": "AI Configuration",
				"tenant": self.tenant.name,
				"enable_erpnext_assistant": 1,
				"enable_erpnext_write_actions": 1,
				"erpnext_assistant_doctypes": "*",
				"require_confirmation_for_sensitive_actions": 1,
				"require_approval_for_sensitive_actions": 1,
				"blocked_ai_action_doctypes": "User,Role,DocType,Custom Field,Property Setter,System Settings",
				"enable_monitoring_alerts": 1,
				"monthly_token_limit": 100,
				"token_usage_alert_percent": 50,
				"pending_approval_alert_hours": 0.001,
				"enable_alert_notifications": 1,
				"alert_notification_cooldown_minutes": 60,
			}
		).insert(ignore_permissions=True)
		self.session = frappe.get_doc(
			{
				"doctype": "AI Chat Session",
				"session_id": f"test-{frappe.generate_hash(length=8)}",
				"tenant": self.tenant.name,
				"platform": "Desk",
				"user_identifier": frappe.session.user,
				"status": "Open",
				"chat_history": "[]",
			}
		).insert(ignore_permissions=True)
		frappe.db.commit()

	def tearDown(self):
		frappe.db.rollback()

	def test_sensitive_action_requires_manager_approval(self):
		result = json.loads(
			tools.crud_erpnext_document(
				self.config,
				action="submit",
				doctype="ToDo",
				name="non-existent",
				confirmed=True,
			)
		)
		self.assertFalse(result.get("success"))
		self.assertTrue(result.get("approval_required"))

	def test_ai_tool_document_sanitizer_redacts_secret_fields(self):
		self.config.provider_api_key = "sk-test-secret"
		data = tools.sanitize_document_for_ai(self.config)
		self.assertEqual(data.get("provider_api_key"), "[redacted]")
		self.assertNotIn("provider_api_key", tools.safe_read_fields("AI Configuration", ["name", "provider_api_key", "model_name"]))
		self.assertIn("model_name", tools.safe_read_fields("AI Configuration", ["name", "provider_api_key", "model_name"]))

	def test_security_doctype_write_is_blocked(self):
		result = json.loads(
			tools.crud_erpnext_document(
				self.config,
				action="update",
				doctype="User",
				name="Administrator",
				values={"first_name": "Blocked"},
				confirmed=True,
			)
		)
		self.assertFalse(result.get("success"))
		self.assertIn("blocked", result.get("error", "").lower())

	def test_stage_and_execute_approved_action(self):
		todo = frappe.get_doc(
			{
				"doctype": "ToDo",
				"description": "Before AI approval",
				"allocated_to": frappe.session.user,
			}
		).insert(ignore_permissions=True)
		result = json.loads(
			tools.stage_ai_action_approval(
				self.config,
				tenant_name=self.tenant.name,
				session_name=self.session.name,
				user_identifier=frappe.session.user,
				platform="Desk",
				action="update",
				doctype="ToDo",
				name=todo.name,
				values={"description": "After AI approval"},
				reason="Integration test approval",
			)
		)
		self.assertTrue(result.get("success"), result)
		approval = frappe.get_doc("AI Action Approval", result.get("approval"))
		approval.status = "Approved"
		approval.save(ignore_permissions=True)
		approval.reload()
		todo.reload()
		self.assertEqual(approval.status, "Executed")
		self.assertEqual(todo.description, "After AI approval")

	def test_tenant_cors_allows_only_configured_domains(self):
		self.assertFalse(tenant_allows_origin(self.tenant.name, "https://example.com"))
		self.tenant.append("allowed_domains", {"domain": "https://www.example.com/path"})
		self.tenant.save(ignore_permissions=True)
		self.assertTrue(tenant_allows_origin(self.tenant.name, "https://app.example.com"))
		self.assertTrue(tenant_allows_origin(self.tenant.name, "https://EXAMPLE.com:443/page"))
		self.assertFalse(tenant_allows_origin(self.tenant.name, "https://evil.test"))
		self.assertFalse(tenant_allows_origin(self.tenant.name, "https://fakeexample.com"))

	def test_chat_sessions_are_tenant_scoped_for_same_public_session_id(self):
		shared_session_id = f"shared-{frappe.generate_hash(length=8)}"
		first = get_or_create_session(self.tenant.name, shared_session_id, "Web", "visitor-a")
		other_tenant = frappe.get_doc({"doctype": "AI Tenant", "tenant_name": f"Other {frappe.generate_hash(length=8)}", "active": 1}).insert(ignore_permissions=True)
		second = get_or_create_session(other_tenant.name, shared_session_id, "Web", "visitor-b")
		self.assertNotEqual(first.name, second.name)
		self.assertEqual(first.tenant, self.tenant.name)
		self.assertEqual(second.tenant, other_tenant.name)
		self.assertNotEqual(first.session_id, second.session_id)

	def test_public_message_validation_rejects_empty_and_oversized_messages(self):
		message, error = validate_public_message("   ")
		self.assertIsNone(message)
		self.assertTrue(error)
		message, error = validate_public_message("x" * 11, max_chars=10)
		self.assertIsNone(message)
		self.assertTrue(error)
		message, error = validate_public_message(" hello ", max_chars=10)
		self.assertEqual(message, "hello")
		self.assertIsNone(error)

	def test_widget_theme_supports_valid_custom_colours_and_legacy_presets(self):
		self.assertEqual(primary_colours("#2F6FED")["primary"], "#2f6fed")
		self.assertEqual(primary_colours("Verity Blue")["primary"], "#0b5ed7")
		self.assertIn("#16345f", header_background("#16345F"))
		self.assertEqual(header_background("Navy Gradient"), "linear-gradient(135deg, #071526 0%, #10233d 58%, #123f78 100%)")

	def test_whatsapp_config_lookup_has_no_default_tenant_fallback_and_dedupes(self):
		self.config.whatsapp_phone_id = f"phone-{frappe.generate_hash(length=8)}"
		self.config.save(ignore_permissions=True)
		self.assertEqual(get_config_for_phone(self.config.whatsapp_phone_id).name, self.config.name)
		self.assertIsNone(get_config_for_phone(f"unknown-{frappe.generate_hash(length=8)}"))
		message_id = f"wamid.{frappe.generate_hash(length=12)}"
		self.assertFalse(is_duplicate_event(self.config, message_id))
		self.assertTrue(is_duplicate_event(self.config, message_id))
	def test_monitoring_alert_deduplicates_open_alerts(self):
		first = create_or_update_alert(
			self.tenant.name,
			"System",
			"test-dedupe-key",
			"Warning",
			"First alert",
			{"count": 1},
		)
		second = create_or_update_alert(
			self.tenant.name,
			"System",
			"test-dedupe-key",
			"High",
			"Second alert",
			{"count": 2},
		)
		self.assertEqual(first.name, second.name)
		second.reload()
		self.assertEqual(second.occurrence_count, 2)
		self.assertEqual(second.severity, "High")

	def test_process_chat_token_limit_block_creates_usage_log_and_alert(self):
		frappe.get_doc(
			{
				"doctype": "AI Usage Log",
				"tenant": self.tenant.name,
				"chat_session": self.session.name,
				"platform": "Desk",
				"provider": "OpenAI",
				"model": "test-model",
				"total_tokens": self.config.monthly_token_limit,
				"status": "Success",
			}
		).insert(ignore_permissions=True)
		session_id = f"limit-{frappe.generate_hash(length=8)}"

		with self.assertRaises(UsageLimitExceeded):
			process_chat(self.tenant.name, session_id, "hello", platform="Web")

		session_name = frappe.db.get_value("AI Chat Session", {"tenant": self.tenant.name, "session_id": session_id}, "name")
		self.assertTrue(session_name)
		blocked_log = frappe.db.get_value("AI Usage Log", {"tenant": self.tenant.name, "chat_session": session_name, "status": "Blocked"}, ["name", "total_tokens"], as_dict=True)
		self.assertTrue(blocked_log)
		self.assertEqual(blocked_log.total_tokens, 0)
		self.assertTrue(frappe.db.exists("AI Monitoring Alert", {"tenant": self.tenant.name, "alert_type": "Token Usage", "dedupe_key": ["like", "token-limit-blocked:%"]}))

	def test_monitor_token_usage_creates_alert(self):
		frappe.get_doc(
			{
				"doctype": "AI Usage Log",
				"tenant": self.tenant.name,
				"chat_session": self.session.name,
				"platform": "Desk",
				"provider": "OpenAI",
				"model": "test-model",
				"input_tokens": 40,
				"output_tokens": 20,
				"total_tokens": 60,
				"status": "Success",
			}
		).insert(ignore_permissions=True)
		alert = monitor_token_usage(self.config)
		self.assertIsNotNone(alert)
		self.assertEqual(alert.alert_type, "Token Usage")

	def test_monitor_pending_approvals_creates_alert(self):
		result = json.loads(
			tools.stage_ai_action_approval(
				self.config,
				tenant_name=self.tenant.name,
				session_name=self.session.name,
				user_identifier=frappe.session.user,
				platform="Desk",
				action="update",
				doctype="ToDo",
				name="TEST-TODO",
				values={"description": "Pending approval"},
			)
		)
		self.assertTrue(result.get("success"), result)
		frappe.db.set_value("AI Action Approval", result.get("approval"), "creation", "2000-01-01 00:00:00", update_modified=False)
		alert = monitor_pending_approvals(self.config)
		self.assertIsNotNone(alert)
		self.assertEqual(alert.alert_type, "Pending Approvals")

	def test_record_whatsapp_failure_creates_alert(self):
		alert = record_whatsapp_failure(
			config=self.config,
			reason="Test WhatsApp failure",
			details="provider error",
			phone_number_id="12345",
			to_number="263000000000",
		)
		self.assertIsNotNone(alert)
		self.assertEqual(alert.alert_type, "WhatsApp Failure")
	def test_alert_notification_due_respects_cooldown(self):
		self.config.admin_whatsapp_number = "263000000001"
		self.config.save(ignore_permissions=True)
		alert = create_or_update_alert(
			self.tenant.name,
			"System",
			"cooldown-test",
			"High",
			"Cooldown test",
		)
		self.assertTrue(alert_notification_due(self.config, alert))
		alert.last_notified = frappe.utils.now_datetime()
		alert.save(ignore_permissions=True)
		self.assertFalse(alert_notification_due(self.config, alert))

	def test_monitoring_summary_counts_open_alerts(self):
		create_or_update_alert(self.tenant.name, "System", "summary-high", "High", "High summary")
		create_or_update_alert(self.tenant.name, "System", "summary-critical", "Critical", "Critical summary")
		summary = get_monitoring_summary(self.tenant.name)
		self.assertTrue(summary.get("success"), summary)
		self.assertGreaterEqual(summary.get("counts", {}).get("high"), 1)
		self.assertGreaterEqual(summary.get("counts", {}).get("critical"), 1)
	def test_action_registry_classifies_blocked_and_high_risk_actions(self):
		self.assertEqual(action_risk("update", "User"), "Blocked")
		self.assertEqual(action_risk("submit", "Sales Invoice"), "High")
		self.assertEqual(action_risk("update", "Customer"), "Medium")

	def test_knowledge_source_rebuilds_chunks(self):
		source = frappe.get_doc(
			{
				"doctype": "AI Knowledge Source",
				"tenant": self.tenant.name,
				"title": "Chunk Test",
				"active": 1,
				"content": " ".join(["knowledge"] * 500),
			}
		).insert(ignore_permissions=True)
		chunks = rebuild_knowledge_chunks(source.name)
		self.assertGreater(len(chunks), 1)
		self.assertGreater(len(chunk_text(source.content)), 1)
		first_hash = frappe.db.get_value("AI Knowledge Chunk", chunks[0], "content_hash")
		self.assertTrue(first_hash)
		self.assertEqual(first_hash, content_hash(frappe.db.get_value("AI Knowledge Chunk", chunks[0], "content")))

	def test_knowledge_chunk_search_scores_relevant_chunks(self):
		source = frappe.get_doc(
			{
				"doctype": "AI Knowledge Source",
				"tenant": self.tenant.name,
				"title": "Support Policy",
				"active": 1,
				"content": "Warranty support includes priority onboarding and renewal assistance. " * 80,
			}
		).insert(ignore_permissions=True)
		rebuild_knowledge_chunks(source.name)
		results = search_knowledge_chunks(self.tenant.name, "priority onboarding warranty", limit=2)
		self.assertTrue(results, results)
		self.assertEqual(results[0].get("title"), "Support Policy")
		self.assertIn("priority onboarding", results[0].get("content", "").lower())
		formatted = tools.search_knowledge_base(self.tenant.name, "priority onboarding warranty", limit=1)
		self.assertIn("Source: Support Policy", formatted)
		self.assertIn("Reference:", formatted)

	def test_semantic_embeddings_are_stored_and_ranked_with_engine_provider(self):
		self.config.enable_semantic_knowledge_search = 1
		self.config.knowledge_embedding_model = "embedding-test"
		self.config.save(ignore_permissions=True)
		first = frappe.get_doc({
			"doctype": "AI Knowledge Source", "tenant": self.tenant.name, "title": "Unrelated wording",
			"active": 1, "content": "The annual protection arrangement covers accidental device failure.",
		}).insert(ignore_permissions=True)
		second = frappe.get_doc({
			"doctype": "AI Knowledge Source", "tenant": self.tenant.name, "title": "Other",
			"active": 1, "content": "Office opening hours and parking instructions.",
		}).insert(ignore_permissions=True)
		rebuild_knowledge_chunks(first.name)
		rebuild_knowledge_chunks(second.name)

		class Embeddings:
			def create(inner_self, model, input):
				vectors = []
				for index, text in enumerate(input):
					value = [1.0, 0.0] if "protection" in text.lower() or "warranty meaning" in text.lower() else [0.0, 1.0]
					vectors.append(SimpleNamespace(index=index, embedding=value))
				return SimpleNamespace(data=vectors)

		client = SimpleNamespace(embeddings=Embeddings())
		with patch("verity_ai.knowledge_index._embedding_client", return_value=client):
			result = embed_knowledge_chunks(tenant=self.tenant.name)
			self.assertEqual(result["embedded"], 2)
			matches = search_knowledge_chunks(self.tenant.name, "warranty meaning", limit=1)
		self.assertEqual(matches[0]["title"], "Unrelated wording")
		self.assertGreater(matches[0]["semantic_score"], 0.9)
		self.assertEqual(frappe.db.count("AI Knowledge Chunk", {"tenant": self.tenant.name, "embedding_status": "Embedded"}), 2)
	def test_retention_cleanup_deletes_old_tenant_logs(self):
		log = frappe.get_doc(
			{
				"doctype": "AI Usage Log",
				"tenant": self.tenant.name,
				"chat_session": self.session.name,
				"platform": "Desk",
				"provider": "OpenAI",
				"model": "test-model",
				"total_tokens": 1,
				"status": "Success",
			}
		).insert(ignore_permissions=True)
		frappe.db.set_value("AI Usage Log", log.name, "creation", "2000-01-01 00:00:00", update_modified=False)
		deleted = cleanup_doctype("AI Usage Log", self.tenant.name, 1)
		self.assertGreaterEqual(deleted, 1)
		self.assertFalse(frappe.db.exists("AI Usage Log", log.name))

	def test_retention_clears_only_old_closed_chat_history(self):
		closed_session = frappe.get_doc(
			{
				"doctype": "AI Chat Session",
				"session_id": f"closed-{frappe.generate_hash(length=8)}",
				"tenant": self.tenant.name,
				"platform": "Web",
				"status": "Closed",
				"chat_history": json.dumps([{"role": "user", "content": "old private message"}]),
			}
		).insert(ignore_permissions=True)
		open_session = frappe.get_doc(
			{
				"doctype": "AI Chat Session",
				"session_id": f"open-{frappe.generate_hash(length=8)}",
				"tenant": self.tenant.name,
				"platform": "Web",
				"status": "Open",
				"chat_history": json.dumps([{"role": "user", "content": "active message"}]),
			}
		).insert(ignore_permissions=True)
		frappe.db.set_value("AI Chat Session", closed_session.name, "modified", "2000-01-01 00:00:00", update_modified=False)
		frappe.db.set_value("AI Chat Session", open_session.name, "modified", "2000-01-01 00:00:00", update_modified=False)

		cleared = cleanup_chat_sessions(self.tenant.name, 1)

		self.assertEqual(cleared, 1)
		self.assertEqual(frappe.db.get_value("AI Chat Session", closed_session.name, "chat_history"), "[]")
		self.assertIn("active message", frappe.db.get_value("AI Chat Session", open_session.name, "chat_history"))

	def test_lead_capture_records_session_and_source_channel(self):
		lead_name = f"Lead {frappe.generate_hash(length=8)}"
		result = json.loads(tools.capture_lead(self.tenant.name, self.session.name, name=lead_name, requirements="Needs implementation help"))
		self.assertTrue(result.get("success"), result)
		lead = frappe.get_doc("AI Lead", result.get("lead_id"))
		self.assertEqual(lead.tenant, self.tenant.name)
		self.assertEqual(lead.chat_session, self.session.name)
		self.assertEqual(lead.source_channel, self.session.platform)

	def test_lead_capture_creates_customer_with_leaf_group(self):
		lead_name = f"Customer Lead {frappe.generate_hash(length=8)}"
		result = json.loads(
			tools.capture_lead(
				self.tenant.name,
				self.session.name,
				name=lead_name,
				email=f"{frappe.generate_hash(length=8)}@example.com",
			)
		)
		self.assertTrue(result.get("success"), result)
		customer_group = frappe.db.get_value("Customer", result.get("customer"), "customer_group")
		self.assertTrue(customer_group)
		self.assertFalse(frappe.db.get_value("Customer Group", customer_group, "is_group"))

	def test_quote_request_records_session_and_source_channel_fields(self):
		quote = frappe.get_doc(
			{
				"doctype": "AI Quotation Request",
				"tenant": self.tenant.name,
				"chat_session": self.session.name,
				"source_channel": "Desk",
				"customer_name": "Context Customer",
				"client_email": "context@example.com",
				"items": "[]",
				"status": "Pending",
			}
		).insert(ignore_permissions=True)
		quote.reload()
		self.assertEqual(quote.chat_session, self.session.name)
		self.assertEqual(quote.source_channel, "Desk")

	def test_control_room_summary_returns_counts(self):
		create_or_update_alert(self.tenant.name, "System", "control-room", "High", "Control room")
		frappe.get_doc(
			{
				"doctype": "AI Usage Log",
				"tenant": self.tenant.name,
				"chat_session": self.session.name,
				"platform": "Desk",
				"provider": "OpenAI",
				"model": "test-model",
				"total_tokens": 25,
				"estimated_cost": 0.01,
				"status": "Success",
			}
		).insert(ignore_permissions=True)
		data = control_room_summary(self.tenant.name)
		self.assertTrue(data.get("success"), data)
		self.assertIn("pending_approvals", data)
		self.assertIn("token_usage", data)
		self.assertGreaterEqual(data.get("token_usage", {}).get("used", 0), 25)
		self.assertIn("pending_approval_rows", data)
		self.assertIn("failed_tool_call_rows", data)
		self.assertIn("quote_approval_rows", data)
		self.assertEqual(len(data.get("activity_trend", [])), 7)
		self.assertGreaterEqual(sum(row.get("tokens", 0) for row in data.get("activity_trend", [])), 25)
		all_tenants = control_room_summary(days=14)
		self.assertEqual(len(all_tenants.get("activity_trend", [])), 14)
		self.assertTrue(any(row.get("name") == self.tenant.name for row in all_tenants.get("tenant_breakdown", [])))

	def test_control_room_summary_includes_action_and_quote_previews(self):
		approval_result = json.loads(
			tools.stage_ai_action_approval(
				self.config,
				tenant_name=self.tenant.name,
				session_name=self.session.name,
				user_identifier=frappe.session.user,
				platform="Desk",
				action="update",
				doctype="ToDo",
				name="TEST-TODO",
				values={"description": "Preview value"},
			)
		)
		self.assertTrue(approval_result.get("success"), approval_result)
		frappe.get_doc(
			{
				"doctype": "AI Quotation Request",
				"tenant": self.tenant.name,
				"customer_name": "Preview Customer",
				"client_whatsapp_number": "263000000003",
				"items": json.dumps([{"item_code": "Service", "qty": 1}]),
				"status": "Pending",
			}
		).insert(ignore_permissions=True)
		data = control_room_summary(self.tenant.name)
		approval_rows = data.get("pending_approval_rows") or []
		quote_rows = data.get("quote_approval_rows") or []
		self.assertTrue(any((row.get("values_preview") or {}).get("description") == "Preview value" for row in approval_rows), approval_rows)
		self.assertTrue(any((row.get("items_preview") or [{}])[0].get("item_code") == "Service" for row in quote_rows), quote_rows)

	def test_control_room_updates_alert_status(self):
		alert = create_or_update_alert(self.tenant.name, "System", "control-room-action", "High", "Actionable alert")
		result = update_alert_status(alert.name, "Acknowledged", note="Reviewed from control room")
		self.assertTrue(result.get("success"), result)
		alert.reload()
		self.assertEqual(alert.status, "Acknowledged")
		details = json.loads(alert.details_json or "{}")
		self.assertEqual(details.get("control_room_notes", [{}])[-1].get("note"), "Reviewed from control room")

	def test_control_room_rejects_action_approval(self):
		result = json.loads(
			tools.stage_ai_action_approval(
				self.config,
				tenant_name=self.tenant.name,
				session_name=self.session.name,
				user_identifier=frappe.session.user,
				platform="Desk",
				action="update",
				doctype="ToDo",
				name="TEST-TODO",
				values={"description": "Should not execute"},
			)
		)
		self.assertTrue(result.get("success"), result)
		approval_name = result.get("approval")
		decision = decide_action_approval(approval_name, "Rejected", note="Not enough context")
		self.assertTrue(decision.get("success"), decision)
		approval = frappe.get_doc("AI Action Approval", approval_name)
		self.assertEqual(approval.status, "Rejected")
		self.assertIn("Not enough context", approval.approval_notes)

	def test_control_room_rejects_quote_request(self):
		quote = frappe.get_doc(
			{
				"doctype": "AI Quotation Request",
				"tenant": self.tenant.name,
				"customer_name": "Control Room Customer",
				"client_whatsapp_number": "263000000002",
				"items": "[]",
				"status": "Pending",
			}
		).insert(ignore_permissions=True)
		result = decide_quote_request(quote.name, "Rejected", note="Needs sales review")
		self.assertTrue(result.get("success"), result)
		quote.reload()
		self.assertEqual(quote.status, "Rejected")
		self.assertIn("Needs sales review", quote.approval_notes)
	def test_setup_wizard_status_and_domain_validation(self):
		self.tenant.append("allowed_domains", {"domain": "example.com"})
		self.tenant.save(ignore_permissions=True)
		data = setup_wizard_status(self.tenant.name)
		self.assertTrue(data.get("success"), data)
		self.assertGreater(data.get("total", 0), 0)
		domains = validate_domains(self.tenant.name)
		self.assertTrue(domains.get("success"), domains)

	def test_public_tool_surface_excludes_service_item_creation(self):
		self.config.enable_erpnext_integration = 1
		self.config.save(ignore_permissions=True)
		web_tool_names = [tool.get("function", {}).get("name") for tool in get_tool_definitions(self.config, platform="Web")]
		desk_tool_names = [tool.get("function", {}).get("name") for tool in get_tool_definitions(self.config, platform="Desk")]
		self.assertNotIn("create_service_item", web_tool_names)
		self.assertIn("create_service_item", desk_tool_names)
		tool_call = SimpleNamespace(function=SimpleNamespace(name="create_service_item", arguments=json.dumps({"item_code": "Unsafe Public Item"})))
		result = json.loads(execute_tool_call(tool_call, self.config, self.tenant.name, self.session, "visitor", platform="Web"))
		self.assertFalse(result.get("success"))
		self.assertIn("unavailable", result.get("error", "").lower())

	def test_chat_runtime_helpers_do_not_raise_missing_imports(self):
		assert_public_rate_limit(self.config, self.tenant.name, session_id=self.session.session_id)
		tool_call = SimpleNamespace(function=SimpleNamespace(name="unknown_tool", arguments="{}"))
		result = json.loads(execute_tool_call(tool_call, self.config, self.tenant.name, self.session, frappe.session.user, platform="Desk"))
		self.assertFalse(result.get("success"))
		self.assertIn("Unknown", result.get("error", ""))
	def test_all_generated_doctypes_exist(self):
		expected = [
			"AI Allowed Domain",
			"AI Business Lead Field",
			"AI Business Nature",
			"AI Tenant",
			"AI Configuration",
			"AI Chat Session",
			"AI Lead",
			"AI Quotation Request",
			"AI Knowledge Source",
			"AI Knowledge Chunk",
			"AI Usage Log",
			"AI Tool Call Log",
			"AI Monitoring Alert",
			"AI Action Approval",
		]
		missing = [doctype for doctype in expected if not frappe.db.exists("DocType", doctype)]
		self.assertFalse(missing, missing)

	def test_workspace_hides_duplicate_custom_document_links(self):
		workspace = frappe.get_doc("Workspace", "Verity AI")
		self.assertTrue(workspace.hide_custom)

	def test_chat_session_id_is_not_globally_unique(self):
		meta = frappe.get_meta("AI Chat Session")
		field = meta.get_field("session_id")
		self.assertFalse(bool(getattr(field, "unique", 0)))

	def test_core_link_fields_support_end_to_end_flows(self):
		expected_links = {
			"AI Configuration": {"tenant": "AI Tenant"},
			"AI Chat Session": {"tenant": "AI Tenant"},
			"AI Lead": {"tenant": "AI Tenant", "chat_session": "AI Chat Session", "customer": "Customer"},
			"AI Quotation Request": {"tenant": "AI Tenant", "chat_session": "AI Chat Session", "customer": "Customer"},
			"AI Usage Log": {"tenant": "AI Tenant", "chat_session": "AI Chat Session"},
			"AI Tool Call Log": {"tenant": "AI Tenant", "chat_session": "AI Chat Session"},
			"AI Monitoring Alert": {"tenant": "AI Tenant"},
			"AI Action Approval": {"tenant": "AI Tenant", "chat_session": "AI Chat Session"},
		}
		for doctype, fields in expected_links.items():
			meta = frappe.get_meta(doctype)
			for fieldname, options in fields.items():
				field = meta.get_field(fieldname)
				self.assertIsNotNone(field, f"{doctype}.{fieldname}")
				self.assertEqual(field.fieldtype, "Link", f"{doctype}.{fieldname}")
				self.assertEqual(field.options, options, f"{doctype}.{fieldname}")

	def test_business_nature_seeds_include_fields(self):
		for name in ("Retail / POS", "Manufacturing", "Professional Services"):
			self.assertTrue(frappe.db.exists("AI Business Nature", name), name)
			doc = frappe.get_doc("AI Business Nature", name)
			self.assertGreater(len(doc.get("lead_fields") or []), 0, name)

	def test_desk_page_asset_folders_exist(self):
		app_root = Path(__file__).resolve().parents[1]
		for folder, js_file in (("ai_control_room", "ai_control_room.js"), ("ai_setup_wizard", "ai_setup_wizard.js")):
			page_dir = app_root / "verity_ai_sales" / "page" / folder
			self.assertTrue(page_dir.exists(), str(page_dir))
			self.assertTrue((page_dir / js_file).exists(), js_file)
