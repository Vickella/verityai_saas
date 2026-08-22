import json
import re
from collections import defaultdict

import frappe
from frappe import _
from frappe.utils import get_url, now_datetime

from verity_ai.tenant_security import normalize_domain

from verityai_saas.services.business_natures import ensure_business_natures, validate_business_nature


TENANT_SAFE_FIELDS = [
	"name", "tenant_name", "assistant_name", "brand_name", "business_nature", "widget_title",
	"widget_greeting", "widget_primary_color", "widget_header_color", "active",
]

WIDGET_PRIMARY_PRESETS = {"Verity Blue", "Navy", "Emerald", "Slate", "Gold"}
WIDGET_HEADER_PRESETS = {"Navy Gradient", "Blue Gradient", "Emerald Gradient", "Slate Gradient"}
HEX_COLOUR = re.compile(r"^#[0-9a-fA-F]{6}$")
WIDGET_ASSET_VERSION = "20260817-2"
CONFIG_SAFE_FIELDS = [
	"model_name", "max_tokens", "monthly_token_limit", "public_rate_limit_per_minute",
	"max_public_message_chars", "enable_monitoring_alerts", "verify_meta_signature",
	"whatsapp_phone_id", "webhook_callback_url", "enable_erpnext_integration",
]

# USD per 1,000 tokens. Kept server-side so cost analytics never depend on a
# customer-provided value. Update this table when provider pricing changes.
MODEL_COSTS_PER_1K = {
	"gpt-4o-mini": (0.00015, 0.00060),
	"gpt-4.1-mini": (0.00040, 0.00160),
}

QUOTE_SAFE_FIELDS = [
	"name", "customer_name", "client_email", "client_whatsapp_number", "status",
	"erpnext_quotation_id", "estimated_total", "sent_file_url", "approval_notes",
	"creation", "modified",
]


def get_workspace(workspace_name):
	if not workspace_name or not frappe.db.exists("VerityAI Workspace", workspace_name):
		frappe.throw(_("Workspace was not found."), frappe.DoesNotExistError)
	return frappe.get_doc("VerityAI Workspace", workspace_name)


def get_workspace_engine_tenant(workspace_name):
	workspace = get_workspace(workspace_name)
	if not workspace.engine_tenant or not frappe.db.exists("AI Tenant", workspace.engine_tenant):
		frappe.throw(_("This workspace is not linked to an engine tenant."), frappe.ValidationError)
	return workspace.engine_tenant


def create_engine_tenant(workspace_name):
	workspace = get_workspace(workspace_name)
	if workspace.engine_tenant and frappe.db.exists("AI Tenant", workspace.engine_tenant):
		return workspace.engine_tenant
	base = frappe.scrub(workspace.workspace_name).replace("_", "-")[:80] or frappe.generate_hash(length=10)
	tenant_name = base
	index = 2
	while frappe.db.exists("AI Tenant", tenant_name):
		tenant_name = f"{base}-{index}"
		index += 1
	tenant = frappe.get_doc({
		"doctype": "AI Tenant", "tenant_name": tenant_name,
		"assistant_name": f"{workspace.business_name} Assistant", "brand_name": workspace.business_name,
		"business_nature": workspace.business_nature, "widget_title": f"Chat with {workspace.business_name}",
		"widget_greeting": "Welcome. How can we help you today?", "active": 1,
	}).insert(ignore_permissions=True)
	workspace.db_set("engine_tenant", tenant.name, update_modified=False)
	return tenant.name


def ensure_engine_configuration(workspace_name):
	tenant = get_workspace(workspace_name).engine_tenant or create_engine_tenant(workspace_name)
	name = frappe.db.get_value("AI Configuration", {"tenant": tenant}, "name")
	if name:
		return name
	config = frappe.get_doc({
		"doctype": "AI Configuration", "tenant": tenant, "model_name": "gpt-4o-mini", "max_tokens": 900,
		"public_rate_limit_per_minute": 20, "max_public_message_chars": 4000,
		"prompt_cost_per_1k": MODEL_COSTS_PER_1K["gpt-4o-mini"][0],
		"completion_cost_per_1k": MODEL_COSTS_PER_1K["gpt-4o-mini"][1],
		"enable_monitoring_alerts": 1, "verify_meta_signature": 0,
	}).insert(ignore_permissions=True)
	return config.name


def get_engine_configuration(workspace_name):
	name = ensure_engine_configuration(workspace_name)
	return frappe.get_doc("AI Configuration", name)


def set_engine_active(workspace_name, active):
	tenant = get_workspace_engine_tenant(workspace_name)
	frappe.db.set_value("AI Tenant", tenant, "active", int(bool(active)))
	return bool(active)


def safe_settings(workspace_name, include_configuration=False):
	tenant = get_workspace_engine_tenant(workspace_name)
	data = frappe.db.get_value("AI Tenant", tenant, TENANT_SAFE_FIELDS, as_dict=True) or {}
	if include_configuration:
		config_name = frappe.db.get_value("AI Configuration", {"tenant": tenant}, "name")
		data["configuration"] = frappe.db.get_value("AI Configuration", config_name, CONFIG_SAFE_FIELDS, as_dict=True) if config_name else {}
	data["allowed_domains"] = frappe.get_all(
		"AI Allowed Domain", filters={"parent": tenant, "parenttype": "AI Tenant"}, pluck="domain", order_by="idx asc"
	)
	data["business_natures"] = ensure_business_natures()
	return data


def update_assistant_identity(workspace_name, values):
	allowed = {"assistant_name", "brand_name", "business_nature", "widget_greeting"}
	values = {key: value for key, value in (values or {}).items() if key in allowed}
	if not values:
		return safe_settings(workspace_name)
	if "business_nature" in values:
		values["business_nature"] = validate_business_nature(values.get("business_nature"), required=True)
	tenant = get_workspace_engine_tenant(workspace_name)
	doc = frappe.get_doc("AI Tenant", tenant)
	for key, value in values.items():
		setattr(doc, key, value)
	doc.save(ignore_permissions=True)
	workspace_values = {"business_name": values.get("brand_name"), "business_nature": values.get("business_nature")}
	workspace_values = {key: value for key, value in workspace_values.items() if value}
	if workspace_values:
		frappe.db.set_value("VerityAI Workspace", workspace_name, workspace_values)
	return safe_settings(workspace_name)


def update_widget_settings(workspace_name, values):
	allowed = {"widget_title", "widget_greeting", "widget_primary_color", "widget_header_color"}
	values = {key: value for key, value in (values or {}).items() if key in allowed}
	if "widget_title" in values:
		values["widget_title"] = str(values["widget_title"] or "").strip()[:120]
		if not values["widget_title"]:
			frappe.throw(_("Widget title is required."), frappe.ValidationError)
	if "widget_greeting" in values:
		values["widget_greeting"] = str(values["widget_greeting"] or "").strip()[:500]
		if not values["widget_greeting"]:
			frappe.throw(_("Widget greeting is required."), frappe.ValidationError)
	for key, presets in (("widget_primary_color", WIDGET_PRIMARY_PRESETS), ("widget_header_color", WIDGET_HEADER_PRESETS)):
		if key not in values:
			continue
		colour = str(values[key] or "").strip()
		if colour not in presets and not HEX_COLOUR.fullmatch(colour):
			frappe.throw(_("Choose a valid six digit colour."), frappe.ValidationError)
		values[key] = colour
	tenant = get_workspace_engine_tenant(workspace_name)
	doc = frappe.get_doc("AI Tenant", tenant)
	for key, value in values.items():
		setattr(doc, key, value)
	doc.save(ignore_permissions=True)
	return safe_settings(workspace_name)


def replace_allowed_domains(workspace_name, domains):
	tenant = get_workspace_engine_tenant(workspace_name)
	clean = []
	for value in domains or []:
		domain = normalize_domain(value)
		if not domain or "*" in str(value) or domain in clean:
			continue
		clean.append(domain)
	plan_name = frappe.db.get_value("VerityAI Subscription", {"workspace": workspace_name, "status": ["in", ["Trial", "Active"]]}, "plan", order_by="creation desc")
	limit = int(frappe.db.get_value("VerityAI Plan", plan_name, "max_allowed_domains") or 0) if plan_name else 0
	if limit and len(clean) > limit:
		frappe.throw(_("Your plan allows up to {0} domains.").format(limit), frappe.ValidationError)
	doc = frappe.get_doc("AI Tenant", tenant)
	doc.set("allowed_domains", [])
	for domain in clean:
		doc.append("allowed_domains", {"domain": domain})
	doc.save(ignore_permissions=True)
	return clean


def generate_embed_code(workspace_name):
	tenant = get_workspace_engine_tenant(workspace_name)
	base = get_url().rstrip("/")
	return f'<script src="{base}/assets/verity_ai/js/widget.js?v={WIDGET_ASSET_VERSION}" data-tenant-id="{tenant}"></script>'


def create_knowledge_source(workspace_name, title, content, file=None):
	tenant = get_workspace_engine_tenant(workspace_name)
	if not title or not (content or file):
		frappe.throw(_("A title and knowledge content or file are required."), frappe.ValidationError)
	plan_name = frappe.db.get_value("VerityAI Subscription", {"workspace": workspace_name, "status": ["in", ["Trial", "Active"]]}, "plan", order_by="creation desc")
	limit = int(frappe.db.get_value("VerityAI Plan", plan_name, "max_knowledge_sources") or 0) if plan_name else 0
	if limit and frappe.db.count("AI Knowledge Source", {"tenant": tenant}) >= limit:
		frappe.throw(_("Your knowledge source plan limit has been reached."), frappe.ValidationError)
	doc = frappe.get_doc({"doctype": "AI Knowledge Source", "tenant": tenant, "title": title, "content": content, "source_file": file, "active": 1})
	doc.insert(ignore_permissions=True)
	return doc.name


def list_knowledge_sources(workspace_name):
	tenant = get_workspace_engine_tenant(workspace_name)
	rows = frappe.get_all("AI Knowledge Source", filters={"tenant": tenant}, fields=["name", "title", "summary", "active", "source_file", "modified"], order_by="modified desc")
	for row in rows:
		row["chunk_count"] = frappe.db.count("AI Knowledge Chunk", {"tenant": tenant, "knowledge_source": row.name})
	return rows


def update_knowledge_source(workspace_name, source_name, values):
	tenant = get_workspace_engine_tenant(workspace_name)
	if not frappe.db.exists("AI Knowledge Source", {"name": source_name, "tenant": tenant}):
		frappe.throw(_("Knowledge source was not found."), frappe.DoesNotExistError)
	doc = frappe.get_doc("AI Knowledge Source", source_name)
	for key in ("title", "content", "summary", "active"):
		if key in values:
			setattr(doc, key, values[key])
	doc.save(ignore_permissions=True)
	return doc.name


def delete_knowledge_source(workspace_name, source_name):
	tenant = get_workspace_engine_tenant(workspace_name)
	if not frappe.db.exists("AI Knowledge Source", {"name": source_name, "tenant": tenant}):
		frappe.throw(_("Knowledge source was not found."), frappe.DoesNotExistError)
	for chunk in frappe.get_all("AI Knowledge Chunk", filters={"tenant": tenant, "knowledge_source": source_name}, pluck="name"):
		frappe.delete_doc("AI Knowledge Chunk", chunk, ignore_permissions=True, force=True)
	for ingestion in frappe.get_all("VerityAI Knowledge Ingestion", filters={"workspace": workspace_name, "knowledge_source": source_name}, pluck="name"):
		frappe.delete_doc("VerityAI Knowledge Ingestion", ingestion, ignore_permissions=True, force=True)
	frappe.delete_doc("AI Knowledge Source", source_name, ignore_permissions=True, force=True)
	return {"deleted": source_name}


def get_workspace_usage(workspace_name, from_date=None, to_date=None):
	tenant = get_workspace_engine_tenant(workspace_name)
	filters = {"tenant": tenant}
	if from_date:
		filters["creation"] = [">=", from_date]
	if from_date and to_date:
		filters["creation"] = ["between", [from_date, to_date]]
	elif to_date:
		filters["creation"] = ["<=", to_date]
	rows = frappe.get_all("AI Usage Log", filters=filters, fields=["name", "platform", "input_tokens", "output_tokens", "total_tokens", "estimated_cost", "status", "creation"], order_by="creation asc")
	data = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0, "estimated_cost": 0.0, "blocked_events": 0, "by_platform": defaultdict(int), "by_date": defaultdict(int)}
	for row in rows:
		data["input_tokens"] += int(row.input_tokens or 0); data["output_tokens"] += int(row.output_tokens or 0); data["total_tokens"] += int(row.total_tokens or 0)
		data["estimated_cost"] += float(row.estimated_cost or 0); data["blocked_events"] += int(row.status == "Blocked")
		data["by_platform"][row.platform or "Unknown"] += int(row.total_tokens or 0); data["by_date"][str(row.creation.date())] += int(row.total_tokens or 0)
	data["by_platform"] = dict(data["by_platform"]); data["by_date"] = dict(data["by_date"]); data["estimated_cost"] = round(data["estimated_cost"], 6)
	return data


def get_workspace_conversations(workspace_name, filters=None):
	tenant = get_workspace_engine_tenant(workspace_name)
	query = {"tenant": tenant}
	filters = filters or {}
	for key in ("platform", "status"):
		if filters.get(key):
			query[key] = filters[key]
	limit = min(max(int(filters.get("limit") or 50), 1), 200)
	start = max(int(filters.get("start") or 0), 0)
	search = (filters.get("search") or "").strip()
	or_filters = None
	if search:
		or_filters = {"session_id": ["like", f"%{search}%"], "user_identifier": ["like", f"%{search}%"]}
	return frappe.get_all("AI Chat Session", filters=query, or_filters=or_filters, fields=["name", "session_id", "platform", "user_identifier", "status", "estimated_deal_value", "modified"], order_by="modified desc", limit_start=start, limit_page_length=limit)

def get_conversation(workspace_name, conversation_name):
	tenant = get_workspace_engine_tenant(workspace_name)
	if not frappe.db.exists("AI Chat Session", {"name": conversation_name, "tenant": tenant}): frappe.throw(_("Conversation was not found."), frappe.DoesNotExistError)
	doc = frappe.get_doc("AI Chat Session", conversation_name)
	try: history = json.loads(doc.chat_history or "[]")
	except (TypeError, ValueError): history = []
	lead = frappe.db.get_value("AI Lead", {"tenant": tenant, "chat_session": doc.name}, "name")
	return {"name": doc.name, "platform": doc.platform, "user_identifier": doc.user_identifier, "status": doc.status, "estimated_deal_value": doc.estimated_deal_value, "history": history, "lead": lead}


def get_workspace_leads(workspace_name, filters=None):
	tenant = get_workspace_engine_tenant(workspace_name)
	filters = filters or {}
	query = {"tenant": tenant}
	for key in ("status", "source_channel"):
		if filters.get(key):
			query[key] = filters[key]
	search = (filters.get("search") or "").strip()
	or_filters = None
	if search:
		or_filters = {"lead_name": ["like", f"%{search}%"], "email": ["like", f"%{search}%"], "phone": ["like", f"%{search}%"]}
	limit = min(max(int(filters.get("limit") or 50), 1), 200)
	start = max(int(filters.get("start") or 0), 0)
	return frappe.get_all("AI Lead", filters=query, or_filters=or_filters, fields=["name", "lead_name", "email", "phone", "source_channel", "status", "chat_session", "dynamic_details", "creation", "modified"], order_by="creation desc", limit_start=start, limit_page_length=limit)

def get_workspace_alerts(workspace_name, filters=None):
	tenant = get_workspace_engine_tenant(workspace_name)
	filters = filters or {}
	query = {"tenant": tenant}
	for key in ("status", "severity"):
		if filters.get(key):
			query[key] = filters[key]
	limit = min(max(int(filters.get("limit") or 20), 1), 200)
	return frappe.get_all(
		"AI Monitoring Alert",
		filters=query,
		fields=["name", "alert_type", "severity", "status", "summary", "occurrence_count", "last_seen", "creation"],
		order_by="last_seen desc",
		limit=limit,
	)


def get_workspace_quote_requests(workspace_name, status=None, limit=100):
	tenant = get_workspace_engine_tenant(workspace_name)
	filters = {"tenant": tenant}
	if status:
		filters["status"] = status
	return frappe.get_all(
		"AI Quotation Request",
		filters=filters,
		fields=QUOTE_SAFE_FIELDS,
		order_by="creation desc",
		limit=min(max(int(limit or 100), 1), 200),
	)


def approve_workspace_quote(workspace_name, quotation_request, notes=None):
	tenant = get_workspace_engine_tenant(workspace_name)
	if not frappe.db.exists("AI Quotation Request", {"name": quotation_request, "tenant": tenant}):
		frappe.throw(_("Quotation request was not found."), frappe.DoesNotExistError)
	doc = frappe.get_doc("AI Quotation Request", quotation_request)
	if doc.status == "Approved":
		return {field: doc.get(field) for field in QUOTE_SAFE_FIELDS}
	if doc.status != "Pending":
		frappe.throw(_("Only pending quotation requests can be approved."), frappe.ValidationError)
	if notes is not None and doc.meta.has_field("approval_notes"):
		doc.approval_notes = str(notes).strip()
	doc.status = "Approved"
	doc.save(ignore_permissions=True)
	doc.reload()
	return {field: doc.get(field) for field in QUOTE_SAFE_FIELDS}


def apply_plan_limits(workspace_name, plan_name):
	get_workspace_engine_tenant(workspace_name)
	plan = frappe.get_doc("VerityAI Plan", plan_name); config = get_engine_configuration(workspace_name)
	for key in ("monthly_token_limit", "max_tokens", "public_rate_limit_per_minute", "max_public_message_chars"):
		setattr(config, key, plan.get(key) or 0)
	model = config.model_name or "gpt-4o-mini"
	if model in MODEL_COSTS_PER_1K:
		config.prompt_cost_per_1k, config.completion_cost_per_1k = MODEL_COSTS_PER_1K[model]
	if not plan.can_use_erpnext_integration: config.enable_erpnext_integration = 0
	if frappe.get_meta("AI Tenant").has_field("show_branding"):
		frappe.db.set_value("AI Tenant", get_workspace_engine_tenant(workspace_name), "show_branding", 0 if plan.can_remove_branding else 1)
	config.save(ignore_permissions=True)
	return {key: config.get(key) for key in ("monthly_token_limit", "max_tokens", "public_rate_limit_per_minute", "max_public_message_chars")}


def whatsapp_status(workspace_name):
	config = get_engine_configuration(workspace_name)
	def present(fieldname):
		try: return bool(config.get_password(fieldname, raise_exception=False))
		except Exception: return False
	return {"phone_id_present": bool(config.whatsapp_phone_id), "access_token_present": present("whatsapp_access_token"), "verify_token_present": bool(config.meta_verify_token), "app_secret_present": present("meta_app_secret"), "signature_verification_enabled": bool(config.verify_meta_signature), "callback_url": f"{get_url().rstrip('/')}/api/method/verity_ai.api.whatsapp.webhook", "checked_at": now_datetime()}
