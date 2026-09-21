import re

import frappe
from frappe.utils import cint, get_url, now_datetime, time_diff_in_hours

from verityai_saas.services.engine import get_engine_configuration
from verityai_saas.services.entitlements import require_workspace_feature


MODES = {"Button Only", "Lead Alerts", "Full AI Automation"}
SECRET_FIELDS = ("whatsapp_access_token", "meta_verify_token", "meta_app_secret")


def _password(doc, fieldname):
	try:
		return doc.get_password(fieldname, raise_exception=False) or ""
	except Exception:
		return ""


def _get_setup(workspace_name, account=None, required=False):
	if account:
		name = frappe.db.get_value("VerityAI WhatsApp Setup", {"name": account, "workspace": workspace_name}, "name")
	else:
		name = frappe.db.get_value("VerityAI WhatsApp Setup", {"workspace": workspace_name, "is_default": 1}, "name", order_by="creation asc")
		name = name or frappe.db.get_value("VerityAI WhatsApp Setup", {"workspace": workspace_name}, "name", order_by="creation asc")
	if required and not name:
		frappe.throw("WhatsApp account was not found.", frappe.DoesNotExistError)
	return frappe.get_doc("VerityAI WhatsApp Setup", name) if name else None


def _unique_phone(setup, phone_id):
	if phone_id and frappe.db.exists("VerityAI WhatsApp Setup", {"whatsapp_phone_id": phone_id, "name": ["!=", setup.name or ""]}):
		frappe.throw("This Meta phone number ID is already connected to another WhatsApp account.", frappe.DuplicateEntryError)


def _make_default(setup):
	for name in frappe.get_all("VerityAI WhatsApp Setup", filters={"workspace": setup.workspace, "is_default": 1, "name": ["!=", setup.name]}, pluck="name"):
		frappe.db.set_value("VerityAI WhatsApp Setup", name, "is_default", 0, update_modified=False)
	setup.is_default = 1


def _sync_legacy_default(setup):
	"""Keep existing engine integrations operating through the selected default account."""
	if not setup.is_default:
		return
	config = get_engine_configuration(setup.workspace)
	config.whatsapp_phone_id = setup.whatsapp_phone_id or None
	config.verify_meta_signature = cint(setup.verify_meta_signature)
	for fieldname in SECRET_FIELDS:
		# A default-account switch must never retain a credential from the
		# previously selected account when the new account omits that secret.
		setattr(config, fieldname, _password(setup, fieldname))
	config.save(ignore_permissions=True)


def configure(workspace_name, values, account=None, creating=False):
	values = frappe._dict(values or {})
	mode = values.get("mode") or "Button Only"
	if mode not in MODES:
		frappe.throw("Unsupported WhatsApp mode.", frappe.ValidationError)
	require_workspace_feature(workspace_name, "can_use_whatsapp_ai" if mode == "Full AI Automation" else "can_use_whatsapp_button", mode)
	setup = None if creating else _get_setup(workspace_name, account)
	if not setup:
		setup = frappe.get_doc({"doctype": "VerityAI WhatsApp Setup", "workspace": workspace_name})
		setup.active = 1
		setup.is_default = int(not frappe.db.exists("VerityAI WhatsApp Setup", {"workspace": workspace_name}))
	label = str(values.get("account_label") or setup.account_label or "Primary WhatsApp").strip()
	if not label or len(label) > 140:
		frappe.throw("A WhatsApp account label is required.", frappe.ValidationError)
	phone_id = str(values.get("whatsapp_phone_id") if "whatsapp_phone_id" in values else setup.whatsapp_phone_id or "").strip()
	_unique_phone(setup, phone_id)
	changed = phone_id != str(setup.whatsapp_phone_id or "").strip()
	setup.update({
		"account_label": label, "mode": mode, "whatsapp_phone_id": phone_id,
		"business_whatsapp_number": values.get("business_whatsapp_number") if "business_whatsapp_number" in values else setup.business_whatsapp_number,
		"whatsapp_button_enabled": cint(values.get("whatsapp_button_enabled", mode == "Button Only")),
		"lead_alert_enabled": cint(values.get("lead_alert_enabled", mode == "Lead Alerts")),
		"full_ai_enabled": cint(mode == "Full AI Automation"),
		"active": cint(values.get("active", setup.active if not setup.is_new() else 1)),
		"verify_meta_signature": cint(values.get("verify_meta_signature", setup.verify_meta_signature if not setup.is_new() else 1)),
	})
	if "reengagement_template_name" in values or "reengagement_template_language" in values:
		old_template = (str(setup.reengagement_template_name or "").strip(), str(setup.reengagement_template_language or "en_US").strip())
		new_template = (
			str(values.get("reengagement_template_name") if "reengagement_template_name" in values else setup.reengagement_template_name or "").strip(),
			str(values.get("reengagement_template_language") if "reengagement_template_language" in values else setup.reengagement_template_language or "en_US").strip() or "en_US",
		)
		setup.reengagement_template_name, setup.reengagement_template_language = new_template
		if new_template != old_template:
			setup.reengagement_template_status = "Not Checked" if new_template[0] else "Not Configured"
	if "meta_waba_id" in values:
		new_waba = str(values.get("meta_waba_id") or "").strip()
		if new_waba != str(setup.meta_waba_id or "").strip():
			setup.meta_waba_id = new_waba
			setup.waba_subscription_status = "Not Checked" if new_waba else "Missing"
			setup.reengagement_template_status = "Not Checked" if setup.reengagement_template_name else "Not Configured"
			changed = True
	for fieldname in SECRET_FIELDS:
		if values.get(fieldname) not in (None, ""):
			setattr(setup, fieldname, values.get(fieldname))
			changed = True
	if cint(values.get("is_default")) or setup.is_default:
		_make_default(setup)
	if mode == "Full AI Automation":
		ready = bool(phone_id and _password(setup, "whatsapp_access_token"))
		if changed or not ready or setup.setup_status != "Connected":
			setup.setup_status = "In Progress"
		setup.update({
			"meta_phone_number_id_status": "Present" if phone_id else "Missing",
			"access_token_status": "Present" if _password(setup, "whatsapp_access_token") else "Missing",
			"webhook_status": "Receiving" if setup.last_webhook_on else "Awaiting Event",
			"signature_verification_status": "Enabled" if setup.verify_meta_signature else "Warning",
		})
	else:
		setup.setup_status = "Connected" if setup.business_whatsapp_number else "In Progress"
	setup.insert(ignore_permissions=True) if setup.is_new() else setup.save(ignore_permissions=True)
	_sync_legacy_default(setup)
	return safe_setup(workspace_name, setup.name)


def create_account(workspace_name, values):
	return configure(workspace_name, values, creating=True)


def set_account_state(workspace_name, account, active=None, is_default=None):
	setup = _get_setup(workspace_name, account, required=True)
	if active is not None:
		setup.active = cint(active)
		if not setup.active and setup.is_default:
			replacement = frappe.db.get_value("VerityAI WhatsApp Setup", {"workspace": workspace_name, "active": 1, "name": ["!=", setup.name]}, "name", order_by="creation asc")
			if replacement:
				setup.is_default = 0
				other = frappe.get_doc("VerityAI WhatsApp Setup", replacement)
				_make_default(other)
				other.save(ignore_permissions=True)
				_sync_legacy_default(other)
	if cint(is_default):
		if not setup.active:
			frappe.throw("Activate the WhatsApp account before making it the default.", frappe.ValidationError)
		_make_default(setup)
	setup.save(ignore_permissions=True)
	_sync_legacy_default(setup)
	return safe_setup(workspace_name, setup.name)


def _account_status(setup):
	return {
		"phone_id_present": bool(setup.whatsapp_phone_id), "access_token_present": bool(_password(setup, "whatsapp_access_token")),
		"verify_token_present": bool(_password(setup, "meta_verify_token")), "app_secret_present": bool(_password(setup, "meta_app_secret")),
		"signature_verification_enabled": bool(setup.verify_meta_signature),
		"callback_url": f"{get_url().rstrip('/')}/api/method/verity_ai.api.whatsapp.webhook", "checked_at": now_datetime(),
	}


def _safe_account(setup):
	fields = ("name", "account_label", "active", "is_default", "mode", "business_whatsapp_number", "whatsapp_button_enabled", "lead_alert_enabled", "full_ai_enabled", "setup_status", "whatsapp_phone_id", "meta_waba_id", "waba_subscription_status", "last_subscription_check_on", "meta_phone_number_id_status", "access_token_status", "webhook_status", "signature_verification_status", "last_tested_on", "last_webhook_on", "last_webhook_event", "reengagement_template_name", "reengagement_template_language", "reengagement_template_status")
	data = {fieldname: setup.get(fieldname) for fieldname in fields}
	data["engine"] = _account_status(setup)
	data["configuration_ready"] = bool(data["engine"]["phone_id_present"] and data["engine"]["access_token_present"] and data["engine"]["verify_token_present"] and (not data["engine"]["signature_verification_enabled"] or data["engine"]["app_secret_present"]))
	data["inbound_verified"] = bool(data.get("last_webhook_on"))
	if data["inbound_verified"]:
		data["setup_status"], data["webhook_status"] = "Connected", "Receiving"
		if data.get("meta_waba_id"):
			data["waba_subscription_status"] = "Subscribed"
	data["webhook_health"] = webhook_health(data)
	return data


def safe_setup(workspace_name, account=None):
	setup = _get_setup(workspace_name, account)
	return _safe_account(setup) if setup else {"engine": {}, "configuration_ready": False, "inbound_verified": False, "webhook_health": {"status": "Not Configured", "message": "No WhatsApp account is configured."}}


def list_accounts(workspace_name):
	return [_safe_account(frappe.get_doc("VerityAI WhatsApp Setup", name)) for name in frappe.get_all("VerityAI WhatsApp Setup", filters={"workspace": workspace_name}, pluck="name", order_by="is_default desc, creation asc")]


def webhook_health(data):
	if data.get("mode") != "Full AI Automation":
		return {"status": "Not Applicable", "message": "Webhook activity is only used by Full AI Automation."}
	if not data.get("last_webhook_on"):
		return {"status": "Awaiting Event", "message": "No inbound WhatsApp event has been processed yet."}
	hours = max(time_diff_in_hours(now_datetime(), data.get("last_webhook_on")), 0)
	return {"status": "Healthy" if hours <= 24 else "Verified", "message": "An inbound WhatsApp event was processed recently." if hours <= 24 else "Inbound delivery was verified previously. No customer message was received in the last 24 hours.", "hours_since_event": round(hours, 1)}


def _record(setup, reference):
	values = {"setup_status": "Connected", "last_webhook_on": now_datetime(), "last_webhook_event": reference or "Inbound WhatsApp message", "webhook_status": "Receiving"}
	if setup.meta_waba_id:
		values["waba_subscription_status"] = "Subscribed"
	frappe.db.set_value("VerityAI WhatsApp Setup", setup.name, values)


def record_channel_activity(doc, method=None):
	if doc.platform == "WhatsApp":
		workspace = frappe.db.get_value("VerityAI Workspace", {"engine_tenant": doc.tenant}, "name")
		setup = _get_setup(workspace) if workspace else None
		if setup:
			_record(setup, doc.name)


def record_inbound_webhook(tenant_name, phone_number_id=None, message_id=None, **kwargs):
	workspace = frappe.db.get_value("VerityAI Workspace", {"engine_tenant": tenant_name}, "name") if tenant_name else None
	if not workspace:
		return
	name = frappe.db.get_value("VerityAI WhatsApp Setup", {"workspace": workspace, "whatsapp_phone_id": phone_number_id}, "name") if phone_number_id else None
	setup = frappe.get_doc("VerityAI WhatsApp Setup", name) if name else _get_setup(workspace)
	if setup:
		_record(setup, message_id)


def test_connection(workspace_name, account=None):
	import requests

	setup = _get_setup(workspace_name, account, required=True)
	phone_id, access_token = str(setup.whatsapp_phone_id or "").strip(), _password(setup, "whatsapp_access_token")
	setup.last_tested_on = checked_at = now_datetime()
	if not setup.active or not phone_id or not access_token:
		setup.setup_status, setup.webhook_status = "Failed", "Credentials Missing"
		setup.save(ignore_permissions=True)
		frappe.throw("An active account, Meta phone number ID, and access token are required.", frappe.ValidationError)
	try:
		response = requests.get(f"https://graph.facebook.com/{_graph_version()}/{phone_id}", headers={"Authorization": f"Bearer {access_token}"}, params={"fields": "id,display_phone_number,verified_name,quality_rating"}, timeout=20)
		payload = response.json() if response.content else {}
	except Exception as exc:
		setup.setup_status, setup.webhook_status = "Failed", "Connection Failed"
		setup.save(ignore_permissions=True)
		frappe.throw(f"Meta connection test failed: {str(exc)[:200]}", frappe.ValidationError)
	if not response.ok or str(payload.get("id") or "") != phone_id:
		error = payload.get("error") if isinstance(payload, dict) else {}
		detail = (error.get("message") if isinstance(error, dict) else None) or response.reason or "Unknown error"
		setup.setup_status, setup.webhook_status = "Failed", "Connection Failed"
		setup.save(ignore_permissions=True)
		frappe.throw(f"Meta rejected the connection test: {detail[:200]}", frappe.ValidationError)
	status = _account_status(setup)
	ready = bool(status["verify_token_present"] and (not status["signature_verification_enabled"] or status["app_secret_present"]))
	receiving = bool(setup.last_webhook_on)
	setup.setup_status = "Connected" if ready and receiving else "In Progress"
	setup.meta_phone_number_id_status, setup.access_token_status = "Verified", "Verified"
	setup.webhook_status = "Receiving" if receiving else "Awaiting Event"
	setup.save(ignore_permissions=True)
	return {"account": setup.name, "connected": bool(ready and receiving), "meta_connected": True, "configuration_ready": ready, "phone_number_id": phone_id, "display_phone_number": payload.get("display_phone_number"), "verified_name": payload.get("verified_name"), "quality_rating": payload.get("quality_rating"), "waba_subscription_status": setup.waba_subscription_status, "checked_at": checked_at, "webhook_health": webhook_health(_safe_account(setup))}


def subscribe_waba(workspace_name, account=None):
	import requests

	setup = _get_setup(workspace_name, account, required=True)
	token, waba_id = _password(setup, "whatsapp_access_token"), str(setup.meta_waba_id or "").strip()
	if not setup.active or not token or not waba_id:
		frappe.throw("An active account, WhatsApp Business Account ID, and access token are required.", frappe.ValidationError)
	version = _graph_version()
	try:
		response = requests.post(f"https://graph.facebook.com/{version}/{waba_id}/subscribed_apps", headers={"Authorization": f"Bearer {token}"}, timeout=20)
		payload = response.json() if response.content else {}
	except Exception as exc:
		frappe.throw(f"Meta WABA subscription failed: {str(exc)[:200]}", frappe.ValidationError)
	if not response.ok or not bool(payload.get("success")):
		error = payload.get("error") if isinstance(payload, dict) else {}
		detail = (error.get("message") if isinstance(error, dict) else None) or response.reason or "Unknown error"
		frappe.throw(f"Meta rejected the WABA subscription: {detail[:200]}", frappe.ValidationError)
	setup.waba_subscription_status, setup.last_subscription_check_on = "Requested", now_datetime()
	setup.save(ignore_permissions=True)
	warning = None
	try:
		verification = _get_waba_subscription(waba_id, token, version)
	except Exception as exc:
		verification, warning = {"subscribed": False, "applications": []}, " ".join(str(exc).split())[:200]
	if verification["subscribed"]:
		setup.waba_subscription_status = "Subscribed"
		setup.save(ignore_permissions=True)
	return {"account": setup.name, "accepted": True, "subscribed": verification["subscribed"], "status": setup.waba_subscription_status, "applications": verification["applications"], "verification_warning": warning, "checked_at": setup.last_subscription_check_on}


def verify_reengagement_template(workspace_name, account=None):
	"""Confirm Meta approved a one-body-variable template for natural edited follow-ups."""
	import requests

	setup = _get_setup(workspace_name, account, required=True)
	token = _password(setup, "whatsapp_access_token")
	waba_id = str(setup.meta_waba_id or "").strip()
	name = str(setup.reengagement_template_name or "").strip()
	language = str(setup.reengagement_template_language or "en_US").strip()
	if not setup.active or not token or not waba_id or not name:
		frappe.throw("An active account, access token, WABA ID, and follow-up template name are required.", frappe.ValidationError)
	try:
		response = requests.get(
			f"https://graph.facebook.com/{_graph_version()}/{waba_id}/message_templates",
			headers={"Authorization": f"Bearer {token}"},
			params={"name": name, "fields": "name,status,language,components", "limit": 100},
			timeout=20,
		)
		payload = response.json() if response.content else {}
	except Exception as exc:
		frappe.throw(f"Meta template verification failed: {str(exc)[:200]}", frappe.ValidationError)
	if not response.ok:
		error = payload.get("error") if isinstance(payload, dict) else {}
		detail = (error.get("message") if isinstance(error, dict) else None) or response.reason or "Unknown error"
		frappe.throw(f"Meta rejected the template check: {detail[:200]}", frappe.ValidationError)
	templates = payload.get("data") if isinstance(payload, dict) else []
	match = next((row for row in templates or [] if row.get("name") == name and row.get("language") == language), None)
	valid, reason = False, "The named language variant was not found."
	if match:
		status = str(match.get("status") or "").upper()
		components = match.get("components") or []
		body = next((row for row in components if str(row.get("type") or "").upper() == "BODY"), {})
		body_variables = set(re.findall(r"\{\{(\d+)\}\}", str(body.get("text") or "")))
		other_variables = set()
		for component in components:
			if component is not body:
				other_variables.update(re.findall(r"\{\{(\d+)\}\}", frappe.as_json(component)))
		valid = status == "APPROVED" and body_variables == {"1"} and not other_variables
		if status != "APPROVED":
			reason = f"Meta reports template status {status or 'UNKNOWN'}."
		elif body_variables != {"1"}:
			reason = "The BODY must contain exactly the {{1}} message variable."
		elif other_variables:
			reason = "Header and button variables are not supported for automatic follow-ups."
		else:
			reason = "Approved and ready for natural edited follow-ups."
	setup.reengagement_template_status = "Approved" if valid else "Rejected"
	setup.save(ignore_permissions=True)
	return {"account": setup.name, "approved": valid, "status": setup.reengagement_template_status, "message": reason, "template": name, "language": language}


def _graph_version():
	version = str(frappe.conf.get("meta_graph_api_version") or "v23.0").strip()
	return version if version.startswith("v") else f"v{version}"


def _get_waba_subscription(waba_id, token, version=None):
	import requests

	response = requests.get(f"https://graph.facebook.com/{version or _graph_version()}/{waba_id}/subscribed_apps", headers={"Authorization": f"Bearer {token}"}, params={"fields": "id,name"}, timeout=20)
	payload = response.json() if response.content else {}
	if not response.ok:
		error = payload.get("error") if isinstance(payload, dict) else {}
		detail = (error.get("message") if isinstance(error, dict) else None) or response.reason or "Unknown error"
		frappe.throw(f"Meta rejected the WABA subscription check: {detail[:200]}", frappe.ValidationError)
	apps = payload.get("data") if isinstance(payload, dict) else []
	apps = apps if isinstance(apps, list) else []
	return {"subscribed": bool(apps), "applications": [{"id": row.get("id"), "name": row.get("name")} for row in apps if isinstance(row, dict)]}
