import json

import frappe
from frappe.utils import cint


def _password(doc, fieldname):
	try:
		return doc.get_password(fieldname, raise_exception=False) or ""
	except Exception:
		return ""


def _migrate_whatsapp_accounts():
	if not frappe.db.exists("DocType", "VerityAI WhatsApp Setup"):
		return
	for row in frappe.get_all(
		"VerityAI WhatsApp Setup",
		fields=["name", "workspace", "account_label", "is_default", "whatsapp_phone_id"],
		order_by="workspace asc, creation asc",
	):
		setup = frappe.get_doc("VerityAI WhatsApp Setup", row.name)
		changed = False
		if not setup.account_label:
			setup.account_label = "Primary WhatsApp"
			changed = True
		if not cint(setup.active):
			setup.active = 1
			changed = True
		if not frappe.db.exists(
			"VerityAI WhatsApp Setup",
			{"workspace": setup.workspace, "is_default": 1, "name": ["!=", setup.name]},
		):
			setup.is_default = 1
			changed = True
		workspace = frappe.db.get_value("VerityAI Workspace", setup.workspace, "engine_tenant")
		config_name = frappe.db.get_value("AI Configuration", {"tenant": workspace}, "name") if workspace else None
		if config_name:
			config = frappe.get_doc("AI Configuration", config_name)
			for target, source in (
				("whatsapp_phone_id", "whatsapp_phone_id"),
				("whatsapp_access_token", "whatsapp_access_token"),
				("meta_verify_token", "meta_verify_token"),
				("meta_app_secret", "meta_app_secret"),
			):
				current = _password(setup, target) if setup.meta.get_field(target).fieldtype == "Password" else setup.get(target)
				legacy = _password(config, source) if config.meta.get_field(source).fieldtype == "Password" else config.get(source)
				if not current and legacy:
					setattr(setup, target, legacy)
					changed = True
			if not setup.verify_meta_signature and config.get("verify_meta_signature"):
				setup.verify_meta_signature = 1
				changed = True
		if changed:
			setup.save(ignore_permissions=True)


def _repair_usage_transactions():
	if not frappe.db.exists("DocType", "VerityAI Usage Transaction"):
		return
	for row in frappe.get_all(
		"VerityAI Usage Transaction",
		filters={"ai_usage_log": ["is", "set"]},
		fields=["name", "workspace", "ai_usage_log", "correlation_id", "transaction_type", "total_tokens"],
	):
		log = frappe.db.get_value(
			"AI Usage Log",
			row.ai_usage_log,
			["status", "platform", "input_tokens", "output_tokens", "total_tokens", "creation"],
			as_dict=True,
		)
		if not log:
			continue
		billable = log.status == "Success"
		transaction_type = "Usage" if billable else "Blocked" if log.status == "Blocked" else "Failed"
		frappe.db.set_value(
			"VerityAI Usage Transaction",
			row.name,
			{
				"transaction_type": transaction_type,
				"total_tokens": cint(log.total_tokens) if billable else 0,
				"operation": "assistant_response",
				"source_feature": (log.platform or "Unknown").lower(),
				"correlation_id": row.correlation_id or f"ai-usage:{row.ai_usage_log}",
				"occurred_on": log.creation,
				"metadata_json": json.dumps({"engine_status": log.status, "provider_tokens": cint(log.total_tokens)}),
			},
			update_modified=False,
		)
	from verityai_saas.services.usage import sync_workspace_usage

	for workspace in frappe.get_all("VerityAI Workspace", pluck="name"):
		sync_workspace_usage(workspace)


def execute():
	from verityai_saas.setup_doctypes import ensure_doctypes

	ensure_doctypes()
	_migrate_whatsapp_accounts()
	_repair_usage_transactions()
	frappe.clear_cache()
