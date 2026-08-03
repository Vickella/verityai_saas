import frappe

from verityai_saas.api._response import endpoint, json_value
from verityai_saas.services.notifications import send_notification
from verityai_saas.services.onboarding import set_step
from verityai_saas.services.permissions import check_workspace_access, require_workspace_permission


SAFE_FIELDS = ["notification_email", "reply_to_email", "lead_notifications_enabled", "daily_summary_enabled", "human_handoff_alerts_enabled", "quote_request_alerts_enabled", "usage_warning_alerts_enabled", "provider_failure_alerts_enabled", "alert_recipients", "email_branding_name", "email_footer", "status"]


@frappe.whitelist()
@endpoint
def get(workspace):
	check_workspace_access(workspace)
	return frappe.db.get_value("VerityAI Notification Setting", {"workspace": workspace}, ["name", *SAFE_FIELDS], as_dict=True) or {}


@frappe.whitelist()
@endpoint
def update(workspace, values):
	require_workspace_permission(workspace, "manage_email")
	values = json_value(values, {})
	name = frappe.db.get_value("VerityAI Notification Setting", {"workspace": workspace}, "name")
	doc = frappe.get_doc("VerityAI Notification Setting", name) if name else frappe.get_doc({"doctype": "VerityAI Notification Setting", "workspace": workspace})
	for key in SAFE_FIELDS:
		if key in values:
			setattr(doc, key, values[key])
	if doc.get("__islocal"):
		doc.insert(ignore_permissions=True)
	else:
		doc.save(ignore_permissions=True)
	set_step(workspace, "email")
	return {key: doc.get(key) for key in SAFE_FIELDS}


@frappe.whitelist()
@endpoint
def send_test(workspace):
	require_workspace_permission(workspace, "manage_email")
	return {"delivery_logs": send_notification(workspace, "Test", "VerityAI notification test", "Your workspace email notifications are configured.")}

