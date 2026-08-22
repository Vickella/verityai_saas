import json

import frappe


ADMIN_ROLE = "Verity AI Administrator"
SALES_ROLE = "Verity AI Sales Manager"
AGENT_ROLE = "Verity AI Agent"
APP_MODULE = "Verity AI Sales"


BASE_SALES_PROMPT = """You are Verity AI, the Client Support Assistant for VerityCore Consultancy.

Public identity:
- Introduce the assistant as Verity AI when appropriate.
- Explain that VerityCore offers VerityPack, VerityPOS, VerityTax, VerityGuard, business systems consulting, forensic assurance, taxation support, risk advisory, reporting, analytics, and software implementation support.
- VerityPack is VerityCore's ERP and business management suite. It supports operations such as accounting, sales, buying, stock, CRM, projects, payroll, HR, manufacturing, reporting, and approvals, depending on the client's setup.
- VerityPOS is for point-of-sale and retail operations.
- VerityTax supports taxation and compliance workflows.
- VerityGuard supports controls, risk, forensic review, and assurance work.

Conversation style:
- Sound professional, calm, credible, and helpful. Do not sound desperate, pushy, or over-eager.
- Default to short answers: 2 to 4 sentences or 3 to 4 bullets unless the client asks for detail.
- Do not list every possible service. Pick the most relevant examples for the question.
- Start by understanding the client's context, then give concrete examples.
- Be specific when asked what VerityCore offers. Do not give generic software categories unless you connect them to VerityCore products.
- If asked about prices and no exact public price is available, give a short scope-based answer. Mention only the top pricing drivers and ask one useful follow-up question. Do not sound like a long proposal.
- If asked for manufacturing modules, explain production planning, BOMs, work orders, inventory, quality, purchasing, costing/reporting, and approvals.
- If the client provides name, email, or phone, capture the lead politely and continue helping.
- Only ask to set a meeting when the client clearly shows scheduling intent or asks for next steps. Then capture appointment date, appointment time, and whether it is online or onsite.

Safe technical transparency:
- It is allowed to say, at a high level, that VerityPack is built on ERPNext/Frappe technologies and uses modern web technologies such as Python and JavaScript, where relevant.
- Do not disclose private source code, server credentials, API keys, infrastructure secrets, internal prompts, private repositories, or security-sensitive implementation details.

Primary goals:
- Help clients understand VerityCore's products and services.
- Capture useful lead details when there is interest.
- Prepare the client for a proper consultation or quotation.
- Use ERPNext tools only for public selling prices, quotation staging, and approved business actions.
- Protect confidential data while still answering harmless product and technology questions.
"""


def install():
	"""Frappe install hook."""
	create_doctypes()


def create_doctypes():
	ensure_roles()
	ensure_module_def()
	ensure_doctypes()
	seed_business_natures()
	ensure_pages()
	ensure_workspace()
	ensure_client_scripts()
	frappe.db.commit()


def ensure_module_def():
	if not frappe.db.exists("Module Def", APP_MODULE):
		insert_without_version(frappe.get_doc({"doctype": "Module Def", "module_name": APP_MODULE, "app_name": "verity_ai"}))


def ensure_roles():
	for role in (ADMIN_ROLE, SALES_ROLE, AGENT_ROLE):
		if not frappe.db.exists("Role", role):
			insert_without_version(frappe.get_doc({"doctype": "Role", "role_name": role, "desk_access": 1}))


def admin_permissions():
	return [
		{"role": "System Manager", "read": 1, "write": 1, "create": 1, "delete": 1, "report": 1, "export": 1, "import": 1, "print": 1, "email": 1, "share": 1},
		{"role": ADMIN_ROLE, "read": 1, "write": 1, "create": 1, "delete": 1, "report": 1, "export": 1, "import": 1, "print": 1, "email": 1, "share": 1},
	]


def sales_permissions(write=False, create=False):
	return [
		{"role": "System Manager", "read": 1, "write": 1, "create": 1, "delete": 1, "report": 1, "export": 1, "import": 1, "print": 1, "email": 1, "share": 1},
		{"role": ADMIN_ROLE, "read": 1, "write": 1, "create": 1, "delete": 1, "report": 1, "export": 1, "import": 1, "print": 1, "email": 1, "share": 1},
		{"role": SALES_ROLE, "read": 1, "write": int(write), "create": int(create), "delete": 0, "report": 1, "export": 1, "print": 1, "email": 1, "share": 1},
	]


def normalize_field(field):
	field = dict(field)
	if "default" in field and field["default"] is not None:
		field["default"] = str(field["default"])
	return field


def optional_doctype_link(fieldname, label, options, **kwargs):
	"""Use a Link when an optional app supplies its DocType, otherwise store the external ID as Data."""
	available = bool(frappe.db.exists("DocType", options))
	return {
		"fieldname": fieldname,
		"label": label,
		"fieldtype": "Link" if available else "Data",
		"options": options if available else None,
		**kwargs,
	}


def save_without_version(doc):
	doc.flags.ignore_version = True
	doc.save(ignore_permissions=True)


def insert_without_version(doc):
	doc.flags.ignore_version = True
	doc.insert(ignore_permissions=True)


def has_import_permission(permissions):
	return any(permission.get("import") for permission in permissions)


def ensure_doctype(name, fields, permissions, **kwargs):
	fields = [normalize_field(field) for field in fields]
	if has_import_permission(permissions) and not kwargs.get("istable"):
		kwargs.setdefault("allow_import", 1)
	if frappe.db.exists("DocType", name):
		doc = frappe.get_doc("DocType", name)
		existing_fields = {field.fieldname: field for field in doc.fields}
		for field in fields:
			existing_field = existing_fields.get(field["fieldname"])
			if existing_field:
				for key, value in field.items():
					setattr(existing_field, key, value)
			else:
				doc.append("fields", field)
		doc.permissions = []
		for permission in permissions:
			doc.append("permissions", permission)
		doc.module = APP_MODULE
		for key, value in kwargs.items():
			setattr(doc, key, value)
		save_without_version(doc)
		print(f"Updated {name}")
		return doc

	doc = frappe.get_doc(
		{
			"doctype": "DocType",
			"name": name,
			"module": APP_MODULE,
			"custom": 1,
			"fields": fields,
			"permissions": permissions,
			**kwargs,
		}
	)
	insert_without_version(doc)
	print(f"Created {name}")
	return doc


def ensure_doctypes():
	ensure_doctype(
		"AI Allowed Domain",
		[
			{
				"fieldname": "domain",
				"label": "Domain Name",
				"fieldtype": "Data",
				"reqd": 1,
				"in_list_view": 1,
				"description": "Example: example.com or app.example.com",
			}
		],
		[],
		istable=1,
	)

	ensure_doctype(
		"AI Business Lead Field",
		[
			{"fieldname": "fieldname", "label": "Fieldname", "fieldtype": "Data", "reqd": 1, "in_list_view": 1},
			{"fieldname": "label", "label": "Label", "fieldtype": "Data", "reqd": 1, "in_list_view": 1},
			{"fieldname": "fieldtype", "label": "Field Type", "fieldtype": "Select", "options": "Data\nSmall Text\nText\nSelect\nInt\nFloat\nCurrency\nDate\nCheck", "default": "Data"},
			{"fieldname": "options", "label": "Options", "fieldtype": "Small Text"},
			{"fieldname": "required", "label": "Required", "fieldtype": "Check"},
			{"fieldname": "description", "label": "Description", "fieldtype": "Small Text"},
		],
		[],
		istable=1,
	)

	ensure_doctype(
		"AI Business Nature",
		[
			{"fieldname": "business_nature", "label": "Business Nature", "fieldtype": "Data", "reqd": 1, "unique": 1, "in_list_view": 1},
			{"fieldname": "description", "label": "Description", "fieldtype": "Small Text"},
			{"fieldname": "lead_fields", "label": "Lead Fields", "fieldtype": "Table", "options": "AI Business Lead Field"},
		],
		admin_permissions(),
		istable=0,
		autoname="field:business_nature",
	)
	ensure_doctype(
		"AI Tenant",
		[
			{"fieldname": "tenant_name", "label": "Tenant Name", "fieldtype": "Data", "reqd": 1, "unique": 1},
			{"fieldname": "assistant_name", "label": "Assistant Name", "fieldtype": "Data", "default": "Verity AI"},
			{"fieldname": "brand_name", "label": "Brand Name", "fieldtype": "Data"},
			{"fieldname": "business_nature", "label": "Business Nature", "fieldtype": "Link", "options": "AI Business Nature"},
			{"fieldname": "widget_title", "label": "Widget Title", "fieldtype": "Data", "default": "Client Support Assistant"},
			{"fieldname": "widget_greeting", "label": "Widget Greeting", "fieldtype": "Small Text", "default": "Welcome. I am here to help with product information, service questions, or anything else you need."},
			{"fieldname": "widget_primary_color", "label": "Widget Primary Colour", "fieldtype": "Data", "default": "#0b5ed7"},
			{"fieldname": "widget_header_color", "label": "Widget Header Colour", "fieldtype": "Data", "default": "#123f78"},
			{"fieldname": "show_branding", "label": "Show VerityAI Branding", "fieldtype": "Check", "default": "1"},
			{"fieldname": "active", "label": "Active", "fieldtype": "Check", "default": "1"},
			{"fieldname": "widget_section", "label": "Website Widget", "fieldtype": "Section Break"},
			{"fieldname": "widget_script_src", "label": "Widget Script URL", "fieldtype": "Data", "read_only": 1},
			{"fieldname": "widget_css_href", "label": "Widget CSS URL", "fieldtype": "Data", "read_only": 1},
			{"fieldname": "website_embed_script", "label": "Website Script Line", "fieldtype": "Code", "options": "HTML", "read_only": 1},
			{"fieldname": "widget_script_url", "label": "Widget Script URL Preview", "fieldtype": "HTML", "hidden": 1},
			{"fieldname": "widget_css_url", "label": "Widget CSS URL Preview", "fieldtype": "HTML", "hidden": 1},
			{"fieldname": "embed_code", "label": "Website Embed Code Preview", "fieldtype": "HTML", "hidden": 1},
			{"fieldname": "allowed_domains", "label": "Allowed Domains", "fieldtype": "Table", "options": "AI Allowed Domain"},
		],
		admin_permissions(),
		istable=0,
		autoname="field:tenant_name",
	)

	ensure_doctype(
		"AI Configuration",
		[
			{"fieldname": "tenant", "label": "Tenant", "fieldtype": "Link", "options": "AI Tenant", "reqd": 1, "unique": 1},
			{"fieldname": "sales_section", "label": "Sales Behavior", "fieldtype": "Section Break"},
			{"fieldname": "system_prompt", "label": "System Prompt", "fieldtype": "Text Editor", "default": BASE_SALES_PROMPT},
			{"fieldname": "temperature", "label": "Temperature", "fieldtype": "Float", "default": "0.35"},
			{"fieldname": "max_tokens", "label": "Max Response Tokens", "fieldtype": "Int", "default": "900"},
			{"fieldname": "human_handoff_threshold", "label": "Human Handoff Deal Value", "fieldtype": "Currency", "default": "10000"},
			{"fieldname": "provider_section", "label": "AI Provider", "fieldtype": "Section Break"},
			{"fieldname": "ai_provider", "label": "AI Provider", "fieldtype": "Select", "options": "OpenAI\nOpenAI-Compatible", "default": "OpenAI"},
			{"fieldname": "model_name", "label": "Model Name", "fieldtype": "Data", "default": "gpt-4o-mini"},
			{"fieldname": "provider_api_base", "label": "Provider API Base URL", "fieldtype": "Data"},
			{"fieldname": "provider_api_key", "label": "Provider API Key", "fieldtype": "Password"},
			{"fieldname": "openai_api_key", "label": "Legacy OpenAI API Key", "fieldtype": "Password", "hidden": 1},
			{"fieldname": "moderation_section", "label": "Confidentiality Firewall", "fieldtype": "Section Break"},
			{"fieldname": "enable_response_moderation", "label": "Moderate Responses Before Sending", "fieldtype": "Check", "default": "0"},
			{"fieldname": "moderation_model_name", "label": "Moderation Model Name", "fieldtype": "Data"},
			{"fieldname": "blocked_response", "label": "Blocked Response", "fieldtype": "Small Text", "default": "I cannot share confidential company information, but I can help you choose the right option or prepare a quote."},
			{"fieldname": "usage_section", "label": "Usage Controls", "fieldtype": "Section Break"},
			{"fieldname": "monthly_token_limit", "label": "Monthly Token Limit", "fieldtype": "Int"},
			{"fieldname": "public_rate_limit_per_minute", "label": "Public Chat Rate Limit / Minute", "fieldtype": "Int", "default": "20"},
			{"fieldname": "max_public_message_chars", "label": "Max Public Message Characters", "fieldtype": "Int", "default": "4000"},
			{"fieldname": "max_history_messages", "label": "Max Model History Messages", "fieldtype": "Int", "default": "24"},
			{"fieldname": "max_history_chars", "label": "Max Model History Characters", "fieldtype": "Int", "default": "24000"},
			{"fieldname": "prompt_cost_per_1k", "label": "Input Cost per 1K Tokens", "fieldtype": "Currency", "default": "0"},
			{"fieldname": "completion_cost_per_1k", "label": "Output Cost per 1K Tokens", "fieldtype": "Currency", "default": "0"},
			{"fieldname": "monitoring_section", "label": "Monitoring & Alerts", "fieldtype": "Section Break"},
			{"fieldname": "enable_monitoring_alerts", "label": "Enable Monitoring Alerts", "fieldtype": "Check", "default": "1"},
			{"fieldname": "tool_error_alert_threshold", "label": "Tool Errors per Hour Alert Threshold", "fieldtype": "Int", "default": "5"},
			{"fieldname": "pending_approval_alert_hours", "label": "Pending Approval Alert Hours", "fieldtype": "Float", "default": "24"},
			{"fieldname": "token_usage_alert_percent", "label": "Token Usage Alert Percent", "fieldtype": "Int", "default": "80"},
			{"fieldname": "whatsapp_failure_alert_threshold", "label": "WhatsApp Failure Alert Threshold", "fieldtype": "Int", "default": "1"},
			{"fieldname": "webhook_event_ttl_seconds", "label": "Webhook Duplicate TTL Seconds", "fieldtype": "Int", "default": "86400"},
			{"fieldname": "enable_alert_notifications", "label": "Send Alert Notifications", "fieldtype": "Check", "default": "1"},
			{"fieldname": "alert_notification_cooldown_minutes", "label": "Alert Notification Cooldown Minutes", "fieldtype": "Int", "default": "60"},
			{"fieldname": "knowledge_section", "label": "Knowledge Retrieval", "fieldtype": "Section Break"},
			{"fieldname": "knowledge_embedding_provider", "label": "Embedding Provider", "fieldtype": "Select", "options": "\nOpenAI\nOpenAI-Compatible", "description": "Reserved for semantic knowledge search."},
			{"fieldname": "knowledge_embedding_model", "label": "Embedding Model", "fieldtype": "Data"},
			{"fieldname": "enable_semantic_knowledge_search", "label": "Enable Semantic Knowledge Search", "fieldtype": "Check", "default": "0"},
			{"fieldname": "retention_section", "label": "Retention", "fieldtype": "Section Break"},
			{"fieldname": "usage_log_retention_days", "label": "Usage Log Retention Days", "fieldtype": "Int", "default": "180"},
			{"fieldname": "tool_log_retention_days", "label": "Tool Log Retention Days", "fieldtype": "Int", "default": "90"},
			{"fieldname": "alert_retention_days", "label": "Alert Retention Days", "fieldtype": "Int", "default": "180"},
			{"fieldname": "chat_session_retention_days", "label": "Closed Chat History Retention Days", "fieldtype": "Int", "default": "365", "description": "Clears chat history for old closed sessions while preserving the session record and links."},
			{"fieldname": "integration_section", "label": "WhatsApp Integration", "fieldtype": "Section Break"},
			{"fieldname": "whatsapp_phone_id", "label": "WhatsApp Phone ID", "fieldtype": "Data"},
			{"fieldname": "whatsapp_access_token", "label": "WhatsApp Access Token", "fieldtype": "Password"},
			{"fieldname": "meta_verify_token", "label": "Meta Verify Token", "fieldtype": "Data", "default": "verity_ai_webhook"},
			{"fieldname": "verify_meta_signature", "label": "Verify Meta Webhook Signature", "fieldtype": "Check", "default": "0"},
			{"fieldname": "meta_app_secret", "label": "Meta App Secret", "fieldtype": "Password"},
			{"fieldname": "webhook_callback_url", "label": "Meta Webhook Callback URL", "fieldtype": "Data", "read_only": 1, "description": "Use this as the Callback URL in Meta Webhooks."},
			{"fieldname": "verify_token", "label": "Legacy Verify Token", "fieldtype": "Password", "default": "verity_ai_webhook", "hidden": 1},
			{"fieldname": "webhook_url", "label": "Meta Webhook Callback URL Preview", "fieldtype": "HTML", "hidden": 1},
			{"fieldname": "meta_setup_details", "label": "Meta App Setup Details", "fieldtype": "HTML", "hidden": 1},
			{"fieldname": "admin_whatsapp_number", "label": "Sales Manager WhatsApp Number", "fieldtype": "Data"},
			{"fieldname": "erpnext_section", "label": "ERPNext Integration", "fieldtype": "Section Break"},
			{"fieldname": "enable_erpnext_integration", "label": "Enable ERPNext Integration", "fieldtype": "Check", "default": "0"},
			{"fieldname": "erpnext_url", "label": "ERPNext URL", "fieldtype": "Data"},
			{"fieldname": "erpnext_api_key", "label": "ERPNext API Key", "fieldtype": "Password"},
			{"fieldname": "erpnext_api_secret", "label": "ERPNext API Secret", "fieldtype": "Password"},
			{"fieldname": "desk_assistant_section", "label": "ERPNext Desk Assistant", "fieldtype": "Section Break"},
			{"fieldname": "enable_erpnext_assistant", "label": "Enable ERPNext Desk Assistant", "fieldtype": "Check", "default": "1"},
			{"fieldname": "erpnext_assistant_doctypes", "label": "Allowed Desk DocTypes", "fieldtype": "Small Text", "default": "*"},
			{"fieldname": "enable_erpnext_write_actions", "label": "Allow Create and Update Actions", "fieldtype": "Check", "default": "1"},
			{"fieldname": "enable_safe_query_tool", "label": "Enable Safe Read-only Query Tool", "fieldtype": "Check", "default": "0"},
			{"fieldname": "require_confirmation_for_sensitive_actions", "label": "Require Confirmation for Sensitive AI Actions", "fieldtype": "Check", "default": "1"},
			{"fieldname": "require_approval_for_sensitive_actions", "label": "Require Manager Approval for Sensitive AI Actions", "fieldtype": "Check", "default": "1"},
			{"fieldname": "blocked_ai_action_doctypes", "label": "Blocked AI Action DocTypes", "fieldtype": "Small Text", "default": "User,Role,Role Profile,DocType,Custom Field,Property Setter,System Settings,Installed Applications,Integration Request,OAuth Client,OAuth Bearer Token,API Key,Social Login Key,Email Account,Email Domain,Print Format,Server Script,Client Script"},
		],
		admin_permissions(),
		istable=0,
	)

	ensure_doctype(
		"AI Chat Session",
		[
			{"fieldname": "session_id", "label": "Session ID", "fieldtype": "Data", "reqd": 1, "unique": 0},
			{"fieldname": "tenant", "label": "Tenant", "fieldtype": "Link", "options": "AI Tenant"},
			{"fieldname": "platform", "label": "Platform", "fieldtype": "Select", "options": "WhatsApp\nWeb\nDesk"},
			{"fieldname": "user_identifier", "label": "User Identifier", "fieldtype": "Data"},
			{"fieldname": "status", "label": "Status", "fieldtype": "Select", "options": "Open\nHuman Handoff\nClosed", "default": "Open"},
			{"fieldname": "estimated_deal_value", "label": "Estimated Deal Value", "fieldtype": "Currency"},
			{"fieldname": "chat_history", "label": "Chat History", "fieldtype": "Code", "options": "JSON"},
		],
		sales_permissions(write=True),
		istable=0,
	)

	ensure_doctype(
		"AI Lead",
		[
			{"fieldname": "lead_name", "label": "Name", "fieldtype": "Data", "reqd": 1, "in_list_view": 1},
			{"fieldname": "email", "label": "Email", "fieldtype": "Data", "options": "Email", "in_list_view": 1},
			{"fieldname": "phone", "label": "Phone", "fieldtype": "Data"},
			optional_doctype_link("customer", "Customer", "Customer", read_only=1),
			{"fieldname": "business_type", "label": "Type of Business", "fieldtype": "Data"},
			{"fieldname": "location", "label": "Location", "fieldtype": "Data"},
			{"fieldname": "enquiry_type", "label": "Enquiry Type", "fieldtype": "Data"},
			{"fieldname": "current_system", "label": "Current System Used", "fieldtype": "Data"},
			{"fieldname": "problems_faced", "label": "Problems Being Faced", "fieldtype": "Small Text"},
			{"fieldname": "requirements", "label": "Requirements", "fieldtype": "Small Text"},
			{"fieldname": "dynamic_details", "label": "Dynamic Lead Details", "fieldtype": "Code", "options": "JSON"},
			{"fieldname": "appointment_section", "label": "Appointment Details", "fieldtype": "Section Break"},
			{"fieldname": "appointment_requested", "label": "Appointment Requested", "fieldtype": "Check"},
			{"fieldname": "appointment_date", "label": "Appointment Date", "fieldtype": "Date"},
			{"fieldname": "appointment_time", "label": "Appointment Time", "fieldtype": "Time"},
			{"fieldname": "appointment_mode", "label": "Appointment Mode", "fieldtype": "Select", "options": "\nOnline\nOnsite"},
			{"fieldname": "appointment_notes", "label": "Appointment Notes", "fieldtype": "Small Text"},
			{"fieldname": "tenant", "label": "Tenant", "fieldtype": "Link", "options": "AI Tenant"},
			{"fieldname": "chat_session", "label": "Chat Session", "fieldtype": "Link", "options": "AI Chat Session"},
			{"fieldname": "source_channel", "label": "Source Channel", "fieldtype": "Data", "read_only": 1, "in_list_view": 1},
			{"fieldname": "status", "label": "Status", "fieldtype": "Select", "options": "New\nContacted\nQualified\nWon\nLost", "default": "New", "in_list_view": 1},
		],
		sales_permissions(write=True, create=True),
		istable=0,
	)

	ensure_doctype(
		"AI Quotation Request",
		[
			{"fieldname": "customer_name", "label": "Customer Name", "fieldtype": "Data", "reqd": 1, "in_list_view": 1},
			{"fieldname": "tenant", "label": "Tenant", "fieldtype": "Link", "options": "AI Tenant"},
			{"fieldname": "chat_session", "label": "Chat Session", "fieldtype": "Link", "options": "AI Chat Session"},
			{"fieldname": "source_channel", "label": "Source Channel", "fieldtype": "Data", "read_only": 1, "in_list_view": 1},
			optional_doctype_link("customer", "VerityPack Customer", "Customer", read_only=1),
			{"fieldname": "client_email", "label": "Client Email", "fieldtype": "Data", "options": "Email"},
			{"fieldname": "client_whatsapp_number", "label": "Client WhatsApp Number", "fieldtype": "Data"},
			{"fieldname": "items", "label": "Items", "fieldtype": "Code", "options": "JSON"},
			{"fieldname": "estimated_total", "label": "Estimated Total", "fieldtype": "Currency"},
			{"fieldname": "client_notes", "label": "Client Notes / Negotiation", "fieldtype": "Small Text"},
			{"fieldname": "status", "label": "Status", "fieldtype": "Select", "options": "Pending\nApproved\nRejected", "default": "Pending", "in_list_view": 1},
			optional_doctype_link("erpnext_quotation_id", "VerityPack Quotation ID", "Quotation"),
			{"fieldname": "sent_to_customer", "label": "Sent To Customer", "fieldtype": "Check", "read_only": 1},
			{"fieldname": "sent_file_url", "label": "Sent PDF URL", "fieldtype": "Data", "read_only": 1},
			{"fieldname": "approval_notes", "label": "Approval Notes", "fieldtype": "Small Text", "read_only": 1},
		],
		sales_permissions(write=True),
		istable=0,
		autoname="REQ-.####",
	)
	ensure_doctype(
		"AI Knowledge Source",
		[
			{"fieldname": "tenant", "label": "Tenant", "fieldtype": "Link", "options": "AI Tenant", "reqd": 1, "in_list_view": 1},
			{"fieldname": "title", "label": "Title", "fieldtype": "Data", "reqd": 1, "in_list_view": 1},
			{"fieldname": "active", "label": "Active", "fieldtype": "Check", "default": "1", "in_list_view": 1},
			{"fieldname": "source_file", "label": "Source File", "fieldtype": "Attach"},
			{"fieldname": "summary", "label": "Summary", "fieldtype": "Small Text"},
			{"fieldname": "content", "label": "Knowledge Content", "fieldtype": "Long Text", "description": "Paste the document text or the key company-specific facts the assistant should use."},
		],
		admin_permissions(),
		istable=0,
	)

	ensure_doctype(
		"AI Knowledge Chunk",
		[
			{"fieldname": "tenant", "label": "Tenant", "fieldtype": "Link", "options": "AI Tenant", "in_list_view": 1},
			{"fieldname": "knowledge_source", "label": "Knowledge Source", "fieldtype": "Link", "options": "AI Knowledge Source", "in_list_view": 1},
			{"fieldname": "title", "label": "Title", "fieldtype": "Data", "in_list_view": 1},
			{"fieldname": "chunk_index", "label": "Chunk", "fieldtype": "Int", "in_list_view": 1},
			{"fieldname": "active", "label": "Active", "fieldtype": "Check", "default": "1", "in_list_view": 1},
			{"fieldname": "content", "label": "Content", "fieldtype": "Long Text"},
			{"fieldname": "content_hash", "label": "Content Hash", "fieldtype": "Data", "in_list_view": 1},
			{"fieldname": "embedding_model", "label": "Embedding Model", "fieldtype": "Data"},
			{"fieldname": "embedding_status", "label": "Embedding Status", "fieldtype": "Select", "options": "Pending\nEmbedded\nFailed", "default": "Pending", "in_list_view": 1},
			{"fieldname": "embedding_vector_json", "label": "Embedding Vector", "fieldtype": "Code", "options": "JSON"},
		],
		admin_permissions(),
		istable=0,
	)
	ensure_doctype(
		"AI Usage Log",
		[
			{"fieldname": "tenant", "label": "Tenant", "fieldtype": "Link", "options": "AI Tenant", "in_list_view": 1},
			{"fieldname": "chat_session", "label": "Chat Session", "fieldtype": "Link", "options": "AI Chat Session"},
			{"fieldname": "platform", "label": "Platform", "fieldtype": "Data"},
			{"fieldname": "provider", "label": "Provider", "fieldtype": "Data", "in_list_view": 1},
			{"fieldname": "model", "label": "Model", "fieldtype": "Data", "in_list_view": 1},
			{"fieldname": "input_tokens", "label": "Input Tokens", "fieldtype": "Int"},
			{"fieldname": "output_tokens", "label": "Output Tokens", "fieldtype": "Int"},
			{"fieldname": "total_tokens", "label": "Total Tokens", "fieldtype": "Int", "in_list_view": 1},
			{"fieldname": "estimated_cost", "label": "Estimated Cost", "fieldtype": "Currency", "in_list_view": 1},
			{"fieldname": "status", "label": "Status", "fieldtype": "Select", "options": "Success\nBlocked\nError", "default": "Success"},
			{"fieldname": "notes", "label": "Notes", "fieldtype": "Small Text"},
		],
		admin_permissions(),
		istable=0,
	)

	ensure_doctype(
		"AI Tool Call Log",
		[
			{"fieldname": "tenant", "label": "Tenant", "fieldtype": "Link", "options": "AI Tenant", "in_list_view": 1},
			{"fieldname": "chat_session", "label": "Chat Session", "fieldtype": "Link", "options": "AI Chat Session", "in_list_view": 1},
			{"fieldname": "platform", "label": "Platform", "fieldtype": "Data", "in_list_view": 1},
			{"fieldname": "user_identifier", "label": "User / Visitor", "fieldtype": "Data", "in_list_view": 1},
			{"fieldname": "tool_name", "label": "Tool Name", "fieldtype": "Data", "in_list_view": 1},
			{"fieldname": "action", "label": "Action", "fieldtype": "Data", "in_list_view": 1},
			{"fieldname": "target_doctype", "label": "Target DocType", "fieldtype": "Data", "in_list_view": 1},
			{"fieldname": "target_name", "label": "Target Name", "fieldtype": "Data", "in_list_view": 1},
			{"fieldname": "status", "label": "Status", "fieldtype": "Select", "options": "Success\nBlocked\nError", "default": "Success", "in_list_view": 1},
			{"fieldname": "duration_ms", "label": "Duration ms", "fieldtype": "Int"},
			{"fieldname": "arguments_json", "label": "Arguments", "fieldtype": "Code", "options": "JSON"},
			{"fieldname": "result_summary", "label": "Result Summary", "fieldtype": "Small Text"},
			{"fieldname": "error", "label": "Error", "fieldtype": "Small Text"},
		],
		admin_permissions(),
		istable=0,
	)

	ensure_doctype(
		"AI Monitoring Alert",
		[
			{"fieldname": "tenant", "label": "Tenant", "fieldtype": "Link", "options": "AI Tenant", "in_list_view": 1},
			{"fieldname": "alert_type", "label": "Alert Type", "fieldtype": "Select", "options": "Tool Failures\nPending Approvals\nToken Usage\nWhatsApp Failure\nSystem", "in_list_view": 1},
			{"fieldname": "severity", "label": "Severity", "fieldtype": "Select", "options": "Info\nWarning\nHigh\nCritical", "default": "Warning", "in_list_view": 1},
			{"fieldname": "status", "label": "Status", "fieldtype": "Select", "options": "Open\nAcknowledged\nResolved", "default": "Open", "in_list_view": 1},
			{"fieldname": "summary", "label": "Summary", "fieldtype": "Small Text", "in_list_view": 1},
			{"fieldname": "details_json", "label": "Details", "fieldtype": "Code", "options": "JSON"},
			{"fieldname": "reference_doctype", "label": "Reference DocType", "fieldtype": "Data"},
			{"fieldname": "reference_name", "label": "Reference Name", "fieldtype": "Data"},
			{"fieldname": "dedupe_key", "label": "Dedupe Key", "fieldtype": "Data", "in_list_view": 1},
			{"fieldname": "occurrence_count", "label": "Occurrences", "fieldtype": "Int", "default": "1", "in_list_view": 1},
			{"fieldname": "first_seen", "label": "First Seen", "fieldtype": "Datetime"},
			{"fieldname": "last_seen", "label": "Last Seen", "fieldtype": "Datetime", "in_list_view": 1},
			{"fieldname": "last_notified", "label": "Last Notified", "fieldtype": "Datetime"},
			{"fieldname": "notification_count", "label": "Notifications", "fieldtype": "Int", "default": "0"},
		],
		admin_permissions(),
		istable=0,
		autoname="AIAL-.####",
	)
	ensure_doctype(
		"AI Action Approval",
		[
			{"fieldname": "tenant", "label": "Tenant", "fieldtype": "Link", "options": "AI Tenant", "in_list_view": 1},
			{"fieldname": "chat_session", "label": "Chat Session", "fieldtype": "Link", "options": "AI Chat Session"},
			{"fieldname": "platform", "label": "Platform", "fieldtype": "Data"},
			{"fieldname": "requested_by", "label": "Requested By", "fieldtype": "Data", "in_list_view": 1},
			{"fieldname": "approved_by", "label": "Approved By", "fieldtype": "Data", "read_only": 1},
			{"fieldname": "status", "label": "Status", "fieldtype": "Select", "options": "Pending\nApproved\nRejected\nExecuted\nFailed", "default": "Pending", "in_list_view": 1},
			{"fieldname": "risk_level", "label": "Risk Level", "fieldtype": "Select", "options": "Medium\nHigh\nCritical", "default": "High", "in_list_view": 1},
			{"fieldname": "action", "label": "Action", "fieldtype": "Data", "in_list_view": 1},
			{"fieldname": "target_doctype", "label": "Target DocType", "fieldtype": "Data", "in_list_view": 1},
			{"fieldname": "target_name", "label": "Target Name", "fieldtype": "Data", "in_list_view": 1},
			{"fieldname": "values_json", "label": "Values", "fieldtype": "Code", "options": "JSON"},
			{"fieldname": "filters_json", "label": "Filters", "fieldtype": "Code", "options": "JSON"},
			{"fieldname": "fields_json", "label": "Fields", "fieldtype": "Code", "options": "JSON"},
			{"fieldname": "approval_notes", "label": "Approval Notes", "fieldtype": "Small Text"},
			{"fieldname": "execution_result", "label": "Execution Result", "fieldtype": "Code", "options": "JSON", "read_only": 1},
		],
		sales_permissions(write=True, create=True),
		istable=0,
		autoname="AIA-.####",
	)



def seed_business_natures():
	seeds = {
		"General Services": [
			{"fieldname": "service_needed", "label": "Service Needed", "fieldtype": "Data", "required": 1},
			{"fieldname": "timeline", "label": "Timeline", "fieldtype": "Data"},
			{"fieldname": "budget_range", "label": "Budget Range", "fieldtype": "Data"},
		],
		"Software / Web Development": [
			{"fieldname": "project_type", "label": "Project Type", "fieldtype": "Data", "required": 1},
			{"fieldname": "preferred_design", "label": "Preferred Design", "fieldtype": "Small Text"},
			{"fieldname": "brand_colours", "label": "Brand Colours", "fieldtype": "Data"},
			{"fieldname": "deadline", "label": "Deadline", "fieldtype": "Data"},
			{"fieldname": "hosting_required", "label": "Hosting Required", "fieldtype": "Check"},
		],
		"Retail / POS": [
			{"fieldname": "number_of_outlets", "label": "Number of Outlets", "fieldtype": "Int"},
			{"fieldname": "pos_devices", "label": "POS Devices", "fieldtype": "Int"},
			{"fieldname": "inventory_size", "label": "Inventory Size", "fieldtype": "Data"},
		],
		"Manufacturing": [
			{"fieldname": "products_made", "label": "Products Made", "fieldtype": "Small Text"},
			{"fieldname": "production_process", "label": "Production Process", "fieldtype": "Small Text"},
			{"fieldname": "stock_tracking_needed", "label": "Stock Tracking Needed", "fieldtype": "Check"},
		],
		"Professional Services": [
			{"fieldname": "practice_area", "label": "Practice Area", "fieldtype": "Data"},
			{"fieldname": "team_size", "label": "Team Size", "fieldtype": "Int"},
			{"fieldname": "reporting_needs", "label": "Reporting Needs", "fieldtype": "Small Text"},
		],
	}
	for name, fields in seeds.items():
		if frappe.db.exists("AI Business Nature", name):
			doc = frappe.get_doc("AI Business Nature", name)
		else:
			doc = frappe.get_doc({"doctype": "AI Business Nature", "business_nature": name})
		doc.description = f"Default lead capture fields for {name}."
		doc.set("lead_fields", [])
		for field in fields:
			doc.append("lead_fields", field)
		if doc.get("__islocal"):
			insert_without_version(doc)
		else:
			save_without_version(doc)
def workspace_shortcuts():
	return [
		{"label": "Control Room", "type": "Page", "link_to": "ai-control-room", "color": "Red"},
		{"label": "Setup Wizard", "type": "Page", "link_to": "ai-setup-wizard", "color": "Blue"},
		{"label": "Tenants", "type": "DocType", "link_to": "AI Tenant", "color": "Green"},
		{"label": "Leads", "type": "DocType", "link_to": "AI Lead", "color": "Cyan"},
		{"label": "Quote Approvals", "type": "DocType", "link_to": "AI Quotation Request", "color": "Orange"},
		{"label": "Monitoring Alerts", "type": "DocType", "link_to": "AI Monitoring Alert", "color": "Red"},
	]


def ensure_page(page_name, title):
	values = {
		"page_name": page_name,
		"title": title,
		"module": APP_MODULE,
		"standard": "No",
	}
	if frappe.db.exists("Page", page_name):
		frappe.db.set_value("Page", page_name, values, update_modified=False)
	else:
		doc = frappe.get_doc({"doctype": "Page", "name": page_name, **values})
		doc.flags.ignore_version = True
		doc.db_insert()


def ensure_pages():
	ensure_page("ai-control-room", "AI Control Room")
	ensure_page("ai-setup-wizard", "AI Setup Wizard")

def workspace_card(label):
	return {"label": label, "type": "Card Break"}


def workspace_doc_link(label, link_to, parent_label):
	return {"label": label, "type": "Link", "link_type": "DocType", "link_to": link_to, "parent_label": parent_label}


def workspace_links():
	return [
		workspace_card("Setup"),
		workspace_doc_link("Tenants", "AI Tenant", "Setup"),
		workspace_doc_link("Configuration", "AI Configuration", "Setup"),
		workspace_doc_link("Business Natures", "AI Business Nature", "Setup"),
		workspace_card("Sales"),
		workspace_doc_link("Leads", "AI Lead", "Sales"),
		workspace_doc_link("Conversations", "AI Chat Session", "Sales"),
		workspace_doc_link("Quote Requests", "AI Quotation Request", "Sales"),
		workspace_card("Operations"),
		workspace_doc_link("Action Approvals", "AI Action Approval", "Operations"),
		workspace_doc_link("Monitoring Alerts", "AI Monitoring Alert", "Operations"),
		workspace_doc_link("Tool Call Logs", "AI Tool Call Log", "Operations"),
		workspace_doc_link("Usage Logs", "AI Usage Log", "Operations"),
		workspace_card("Knowledge"),
		workspace_doc_link("Knowledge Sources", "AI Knowledge Source", "Knowledge"),
		workspace_doc_link("Knowledge Chunks", "AI Knowledge Chunk", "Knowledge"),
	]

def workspace_content():
	content = [{"type": "header", "data": {"text": "Verity AI", "col": 12}}]
	for shortcut in workspace_shortcuts():
		content.append(
			{
				"type": "shortcut",
				"data": {
					"shortcut_name": shortcut["label"],
					"col": 2,
					"type": shortcut["type"],
					"link_to": shortcut["link_to"],
					"color": shortcut["color"],
				},
			}
		)
	for card_name in ("Setup", "Sales", "Operations", "Knowledge"):
		content.append({"type": "card", "data": {"card_name": card_name, "col": 3}})
	return content


def set_child_table(doc, table_name, rows):
	if not hasattr(doc, "append"):
		return
	try:
		if hasattr(doc, "set"):
			doc.set(table_name, [])
		else:
			setattr(doc, table_name, [])
		for row in rows:
			doc.append(table_name, row)
	except Exception:
		# Frappe versions differ slightly in Workspace child tables. The content JSON still renders the workspace.
		frappe.log_error(title="Verity AI Workspace Child Table Error", message=frappe.get_traceback())


def populate_workspace(doc):
	set_child_table(doc, "shortcuts", workspace_shortcuts())
	set_child_table(doc, "links", workspace_links())


def ensure_workspace():
	workspace_name = "Verity AI"
	legacy_workspace_name = "Verity AI Sales"
	values = {
		"title": "Verity AI",
		"label": "Verity AI",
		"module": APP_MODULE,
		"icon": "sales-order",
		"type": "Custom",
		"public": 1,
		"is_standard": 0,
		"hide_custom": 1,
		"content": json.dumps(workspace_content()),
	}
	if frappe.db.exists("Workspace", legacy_workspace_name):
		legacy = frappe.get_doc("Workspace", legacy_workspace_name)
		legacy.public = 0
		save_without_version(legacy)
	if frappe.db.exists("Workspace", workspace_name):
		doc = frappe.get_doc("Workspace", workspace_name)
		doc.update(values)
		populate_workspace(doc)
		save_without_version(doc)
	else:
		doc = frappe.get_doc({"doctype": "Workspace", "name": workspace_name, **values})
		populate_workspace(doc)
		insert_without_version(doc)

def ensure_client_scripts():
	upsert_client_script(
		"AI Tenant Embed Script",
		"AI Tenant",
		"""
frappe.ui.form.on('AI Tenant', {
	refresh(frm) {
		if (!frm.doc.tenant_name) {
			frm.set_value('widget_script_src', '');
			frm.set_value('widget_css_href', '');
			frm.set_value('website_embed_script', '');
			return;
		}

		const baseUrl = window.location.origin;
		const scriptUrl = `${baseUrl}/assets/verity_ai/js/widget.js`;
		const cssUrl = `${baseUrl}/assets/verity_ai/css/widget.css`;
		const embedCode = `<!-- Verity AI Widget -->\n<script src="${scriptUrl}" data-tenant-id="${frm.doc.tenant_name}" data-assistant-name="${frm.doc.assistant_name || 'Verity AI'}" data-widget-title="${frm.doc.widget_title || 'Client Support Assistant'}"></script>`;

		frm.set_value('widget_script_src', scriptUrl);
		frm.set_value('widget_css_href', cssUrl);
		frm.set_value('website_embed_script', embedCode);
	},
	tenant_name(frm) {
		frm.trigger('refresh');
	}
});
""",
	)
	upsert_client_script(
		"AI Configuration Integration Script",
		"AI Configuration",
		"""
frappe.ui.form.on('AI Configuration', {
	refresh(frm) {
		const baseUrl = window.location.origin;
		const webhook = `${baseUrl}/api/method/verity_ai.api.whatsapp.webhook`;
		const verifyToken = frm.doc.meta_verify_token || frm.doc.verify_token || 'verity_ai_webhook';

		if (!frm.doc.meta_verify_token) {
			frm.set_value('meta_verify_token', verifyToken);
		}
		frm.set_value('webhook_callback_url', webhook);
	}
});
""",
	)

def upsert_client_script(name, dt, script):
	if frappe.db.exists("Client Script", name):
		doc = frappe.get_doc("Client Script", name)
		doc.dt = dt
		doc.view = "Form"
		doc.script = script
		doc.enabled = 1
		save_without_version(doc)
	else:
		insert_without_version(frappe.get_doc({"doctype": "Client Script", "name": name, "dt": dt, "view": "Form", "script": script, "enabled": 1}))
