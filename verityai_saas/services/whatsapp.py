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
	if "meta_waba_id" in values:
		new_waba_id = str(values.get("meta_waba_id") or "").strip()
		if new_waba_id != str(setup.get("meta_waba_id") or "").strip():
			setup.meta_waba_id = new_waba_id
			setup.waba_subscription_status = "Not Checked" if new_waba_id else "Missing"
	if mode == "Full AI Automation":
		config = get_engine_configuration(workspace_name)
		connection_changed = False
		for key in ("whatsapp_phone_id", "whatsapp_access_token", "meta_verify_token", "meta_app_secret", "verify_meta_signature"):
			if key in values and values[key] not in (None, ""):
				if key == "verify_meta_signature":
					connection_changed = connection_changed or int(bool(values[key])) != int(bool(config.get(key)))
				elif key == "whatsapp_phone_id":
					connection_changed = connection_changed or str(values[key]).strip() != str(config.get(key) or "").strip()
				else:
					# Secret fields are write-only. A submitted value is therefore an
					# intentional credential rotation even when its plaintext cannot be
					# compared with the stored encrypted password.
					connection_changed = True
				setattr(config, key, values[key])
		config.save(ignore_permissions=True)
		status = whatsapp_status(workspace_name)
		credentials_present = status["phone_id_present"] and status["access_token_present"]
		if connection_changed or not credentials_present or setup.setup_status != "Connected":
			setup.setup_status = "In Progress"
		setup.update({
			"meta_phone_number_id_status": "Present" if status["phone_id_present"] else "Missing",
			"access_token_status": "Present" if status["access_token_present"] else "Missing",
			"webhook_status": "Receiving" if setup.last_webhook_on else "Awaiting Event",
			"signature_verification_status": "Enabled" if status["signature_verification_enabled"] else "Warning",
		})
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
	fields = ("mode", "business_whatsapp_number", "whatsapp_button_enabled", "lead_alert_enabled", "full_ai_enabled", "setup_status", "meta_waba_id", "waba_subscription_status", "last_subscription_check_on", "meta_phone_number_id_status", "access_token_status", "webhook_status", "signature_verification_status", "last_tested_on", "last_webhook_on", "last_webhook_event")
	data = {key: setup.get(key) for key in fields} if setup else {}
	data["engine"] = whatsapp_status(workspace_name)
	data["whatsapp_phone_id"] = get_engine_configuration(workspace_name).whatsapp_phone_id or ""
	data["configuration_ready"] = bool(
		data["engine"]["phone_id_present"]
		and data["engine"]["access_token_present"]
		and data["engine"]["verify_token_present"]
		and (not data["engine"]["signature_verification_enabled"] or data["engine"]["app_secret_present"])
	)
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
			"setup_status": "Connected",
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
	if not version.startswith("v"):
		version = f"v{version}"
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
	if str(payload.get("id") or "") != phone_id:
		setup.setup_status = "Failed"
		setup.webhook_status = "Connection Failed"
		setup.save(ignore_permissions=True)
		frappe.throw("Meta returned a different phone number ID.", frappe.ValidationError)
	status = whatsapp_status(workspace_name)
	inbound_ready = bool(
		status["verify_token_present"]
		and (not status["signature_verification_enabled"] or status["app_secret_present"])
	)
	webhook_receiving = bool(setup.last_webhook_on)
	# A successful Graph API request proves the credentials and phone-number ID,
	# but it does not prove that Meta can deliver inbound webhook events. Only an
	# actual inbound WhatsApp session may move the channel to Connected.
	setup.setup_status = "Connected" if inbound_ready and webhook_receiving else "In Progress"
	setup.meta_phone_number_id_status = "Verified"
	setup.access_token_status = "Verified"
	if setup.meta_waba_id:
		subscription = _get_waba_subscription(setup.meta_waba_id, access_token, version)
		setup.waba_subscription_status = "Subscribed" if subscription["subscribed"] else "Not Subscribed"
		setup.last_subscription_check_on = checked_at
	setup.webhook_status = "Receiving" if setup.last_webhook_on else "Awaiting Event"
	setup.save(ignore_permissions=True)
	return {
		"connected": bool(inbound_ready and webhook_receiving),
		"meta_connected": True,
		"configuration_ready": inbound_ready,
		"phone_number_id": payload.get("id") or phone_id,
		"display_phone_number": payload.get("display_phone_number"),
		"verified_name": payload.get("verified_name"),
		"quality_rating": payload.get("quality_rating"),
		"waba_subscription_status": setup.waba_subscription_status,
		"checked_at": checked_at,
		"webhook_health": webhook_health(safe_setup(workspace_name)),
	}


def subscribe_waba(workspace_name):
	"""Subscribe the Meta app represented by the access token to this WABA."""
	import requests

	config = get_engine_configuration(workspace_name)
	access_token = config.get_password("whatsapp_access_token", raise_exception=False)
	setup_name = frappe.db.get_value("VerityAI WhatsApp Setup", {"workspace": workspace_name}, "name")
	if not setup_name:
		frappe.throw("WhatsApp setup was not found.", frappe.DoesNotExistError)
	setup = frappe.get_doc("VerityAI WhatsApp Setup", setup_name)
	waba_id = str(setup.meta_waba_id or "").strip()
	if not waba_id or not access_token:
		frappe.throw("WhatsApp Business Account ID and access token are required.", frappe.ValidationError)
	version = _graph_version()
	url = f"https://graph.facebook.com/{version}/{waba_id}/subscribed_apps"
	try:
		response = requests.post(url, headers={"Authorization": f"Bearer {access_token}"}, timeout=20)
		payload = response.json() if response.content else {}
	except Exception as exc:
		frappe.throw(f"Meta WABA subscription failed: {str(exc)[:200]}", frappe.ValidationError)
	if not response.ok or not bool(payload.get("success")):
		error = payload.get("error") if isinstance(payload, dict) else {}
		message = error.get("message") if isinstance(error, dict) else None
		frappe.throw(f"Meta rejected the WABA subscription: {(message or response.reason or 'Unknown error')[:200]}", frappe.ValidationError)
	checked_at = now_datetime()
	verification = _get_waba_subscription(waba_id, access_token, version)
	setup.waba_subscription_status = "Subscribed" if verification["subscribed"] else "Not Subscribed"
	setup.last_subscription_check_on = checked_at
	setup.save(ignore_permissions=True)
	return {
		"subscribed": verification["subscribed"],
		"applications": verification["applications"],
		"checked_at": checked_at,
	}


def _graph_version():
	version = (frappe.conf.get("meta_graph_api_version") or "v23.0").strip()
	return version if version.startswith("v") else f"v{version}"


def _get_waba_subscription(waba_id, access_token, version=None):
	import requests

	version = version or _graph_version()
	url = f"https://graph.facebook.com/{version}/{str(waba_id).strip()}/subscribed_apps"
	try:
		response = requests.get(
			url,
			headers={"Authorization": f"Bearer {access_token}"},
			params={"fields": "id,name"},
			timeout=20,
		)
		payload = response.json() if response.content else {}
	except Exception as exc:
		frappe.throw(f"Meta WABA subscription check failed: {str(exc)[:200]}", frappe.ValidationError)
	if not response.ok:
		error = payload.get("error") if isinstance(payload, dict) else {}
		message = error.get("message") if isinstance(error, dict) else None
		frappe.throw(f"Meta rejected the WABA subscription check: {(message or response.reason or 'Unknown error')[:200]}", frappe.ValidationError)
	applications = payload.get("data") if isinstance(payload, dict) else []
	applications = applications if isinstance(applications, list) else []
	return {
		"subscribed": bool(applications),
		"applications": [{"id": row.get("id"), "name": row.get("name")} for row in applications if isinstance(row, dict)],
	}
