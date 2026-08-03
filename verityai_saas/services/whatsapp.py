import frappe

from verityai_saas.services.engine import get_engine_configuration, whatsapp_status


MODES = {"Button Only", "Lead Alerts", "Full AI Automation"}


def configure(workspace_name, values):
	values = values or {}
	mode = values.get("mode") or "Button Only"
	if mode not in MODES:
		frappe.throw("Unsupported WhatsApp mode.", frappe.ValidationError)
	name = frappe.db.get_value("VerityAI WhatsApp Setup", {"workspace": workspace_name}, "name")
	setup = frappe.get_doc("VerityAI WhatsApp Setup", name) if name else frappe.get_doc({"doctype": "VerityAI WhatsApp Setup", "workspace": workspace_name})
	setup.update({"mode": mode, "business_whatsapp_number": values.get("business_whatsapp_number"), "whatsapp_button_enabled": int(bool(values.get("whatsapp_button_enabled", mode == "Button Only"))), "lead_alert_enabled": int(bool(values.get("lead_alert_enabled", mode == "Lead Alerts"))), "full_ai_enabled": int(mode == "Full AI Automation")})
	if mode == "Full AI Automation":
		config = get_engine_configuration(workspace_name)
		for key in ("whatsapp_phone_id", "whatsapp_access_token", "meta_verify_token", "meta_app_secret", "verify_meta_signature"):
			if key in values and values[key] not in (None, ""):
				setattr(config, key, values[key])
		config.save(ignore_permissions=True)
		status = whatsapp_status(workspace_name)
		setup.update({"setup_status": "Connected" if status["phone_id_present"] and status["access_token_present"] else "In Progress", "meta_phone_number_id_status": "Present" if status["phone_id_present"] else "Missing", "access_token_status": "Present" if status["access_token_present"] else "Missing", "webhook_status": "Ready", "signature_verification_status": "Enabled" if status["signature_verification_enabled"] else "Warning"})
	else:
		setup.setup_status = "Connected" if setup.business_whatsapp_number else "In Progress"
	if setup.get("__islocal"):
		setup.insert(ignore_permissions=True)
	else:
		setup.save(ignore_permissions=True)
	return safe_setup(workspace_name)


def safe_setup(workspace_name):
	name = frappe.db.get_value("VerityAI WhatsApp Setup", {"workspace": workspace_name}, "name")
	setup = frappe.get_doc("VerityAI WhatsApp Setup", name) if name else None
	fields = ("mode", "business_whatsapp_number", "whatsapp_button_enabled", "lead_alert_enabled", "full_ai_enabled", "setup_status", "meta_phone_number_id_status", "access_token_status", "webhook_status", "signature_verification_status", "last_tested_on")
	data = {key: setup.get(key) for key in fields} if setup else {}
	data["engine"] = whatsapp_status(workspace_name)
	return data

