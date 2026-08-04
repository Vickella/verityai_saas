import frappe
from frappe.utils import now_datetime, time_diff_in_hours

from verityai_saas.services.engine import get_engine_configuration, whatsapp_status
from verityai_saas.services.entitlements import require_workspace_feature


MODES = {"Button Only", "Lead Alerts", "Full AI Automation"}


def configure(workspace_name, values):
	values = values or {}
	mode = values.get("mode") or "Button Only"
	if mode not in MODES:
		frappe.throw("Unsupported WhatsApp mode.", frappe.ValidationError)
	feature = "can_use_whatsapp_ai" if mode == "Full AI Automation" else "can_use_whatsapp_button"
	require_workspace_feature(workspace_name, feature, mode)
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
	fields = ("mode", "business_whatsapp_number", "whatsapp_button_enabled", "lead_alert_enabled", "full_ai_enabled", "setup_status", "meta_phone_number_id_status", "access_token_status", "webhook_status", "signature_verification_status", "last_tested_on", "last_webhook_on", "last_webhook_event")
	data = {key: setup.get(key) for key in fields} if setup else {}
	data["engine"] = whatsapp_status(workspace_name)
	data["webhook_health"] = webhook_health(data)
	return data



def webhook_health(setup_data):
	if setup_data.get("mode") != "Full AI Automation":
		return {"status": "Not Applicable", "message": "Webhook activity is only used by Full AI Automation."}
	last_webhook_on = setup_data.get("last_webhook_on")
	if not last_webhook_on:
		return {"status": "Awaiting Event", "message": "No inbound WhatsApp event has been processed yet."}
	hours = max(time_diff_in_hours(now_datetime(), last_webhook_on), 0)
	if hours <= 24:
		return {"status": "Healthy", "message": "An inbound WhatsApp event was processed recently.", "hours_since_event": round(hours, 1)}
	return {"status": "Stale", "message": "No inbound WhatsApp event has been processed in the last 24 hours.", "hours_since_event": round(hours, 1)}


def record_channel_activity(doc, method=None):
	if doc.platform != "WhatsApp":
		return
	workspace = frappe.db.get_value("VerityAI Workspace", {"engine_tenant": doc.tenant}, "name")
	setup = frappe.db.get_value("VerityAI WhatsApp Setup", {"workspace": workspace}, "name") if workspace else None
	if setup:
		frappe.db.set_value("VerityAI WhatsApp Setup", setup, {
			"last_webhook_on": now_datetime(),
			"last_webhook_event": doc.name,
			"webhook_status": "Receiving",
		})


def test_connection(workspace_name):
	import requests

	config = get_engine_configuration(workspace_name)
	phone_id = (config.whatsapp_phone_id or "").strip()
	access_token = config.get_password("whatsapp_access_token", raise_exception=False)
	setup_name = frappe.db.get_value("VerityAI WhatsApp Setup", {"workspace": workspace_name}, "name")
	if not setup_name:
		frappe.throw("WhatsApp setup was not found.", frappe.DoesNotExistError)
	setup = frappe.get_doc("VerityAI WhatsApp Setup", setup_name)
	checked_at = now_datetime()
	setup.last_tested_on = checked_at
	if not phone_id or not access_token:
		setup.setup_status = "Failed"
		setup.webhook_status = "Credentials Missing"
		setup.save(ignore_permissions=True)
		frappe.throw("Meta phone number ID and access token are required.", frappe.ValidationError)
	version = (frappe.conf.get("meta_graph_api_version") or "v23.0").strip()
	url = f"https://graph.facebook.com/{version}/{phone_id}"
	try:
		response = requests.get(
			url,
			headers={"Authorization": f"Bearer {access_token}"},
			params={"fields": "id,display_phone_number,verified_name,quality_rating"},
			timeout=20,
		)
		payload = response.json() if response.content else {}
	except Exception as exc:
		setup.setup_status = "Failed"
		setup.webhook_status = "Connection Failed"
		setup.save(ignore_permissions=True)
		frappe.throw(f"Meta connection test failed: {str(exc)[:200]}", frappe.ValidationError)
	if not response.ok:
		error = payload.get("error") if isinstance(payload, dict) else {}
		message = error.get("message") if isinstance(error, dict) else None
		setup.setup_status = "Failed"
		setup.webhook_status = "Connection Failed"
		setup.save(ignore_permissions=True)
		frappe.throw(f"Meta rejected the connection test: {(message or response.reason or 'Unknown error')[:200]}", frappe.ValidationError)
	setup.setup_status = "Connected"
	setup.meta_phone_number_id_status = "Verified"
	setup.access_token_status = "Verified"
	setup.webhook_status = "Ready" if not setup.last_webhook_on else "Receiving"
	setup.save(ignore_permissions=True)
	return {
		"connected": True,
		"phone_number_id": payload.get("id") or phone_id,
		"display_phone_number": payload.get("display_phone_number"),
		"verified_name": payload.get("verified_name"),
		"quality_rating": payload.get("quality_rating"),
		"checked_at": checked_at,
		"webhook_health": webhook_health(safe_setup(workspace_name)),
	}