from html import escape

import frappe
from frappe.utils import now_datetime


def workspace_for_tenant(tenant):
	return frappe.db.get_value("VerityAI Workspace", {"engine_tenant": tenant}, "name")


def recipients(setting):
	values = [setting.notification_email] + (setting.alert_recipients or "").replace(";", ",").split(",")
	return sorted({value.strip() for value in values if value and value.strip()})


def send_notification(workspace_name, notification_type, subject, message, reference_doctype=None, reference_name=None):
	setting_name = frappe.db.get_value("VerityAI Notification Setting", {"workspace": workspace_name, "status": "Active"}, "name")
	if not setting_name:
		return []
	setting = frappe.get_doc("VerityAI Notification Setting", setting_name)
	branding = escape(setting.email_branding_name or "VerityAI")
	body = escape(message).replace("\n", "<br>")
	footer = escape(setting.email_footer or "").replace("\n", "<br>")
	email_body = f"<p><strong>{branding}</strong></p><p>{body}</p>"
	if footer:
		email_body += f"<p>{footer}</p>"
	logs = []
	for recipient in recipients(setting):
		log = frappe.get_doc({"doctype": "VerityAI Email Delivery Log", "workspace": workspace_name, "notification_type": notification_type, "recipient": recipient, "subject": subject, "status": "Pending", "reference_doctype": reference_doctype, "reference_name": reference_name}).insert(ignore_permissions=True)
		try:
			frappe.sendmail(recipients=[recipient], subject=subject, message=email_body, reply_to=setting.reply_to_email or None)
			log.status, log.sent_on = "Sent", now_datetime()
		except Exception as exc:
			log.status, log.error = "Failed", str(exc)[:500]
		log.save(ignore_permissions=True)
		logs.append(log.name)
	return logs


def send_lead_notification(doc, method=None):
	workspace = workspace_for_tenant(doc.tenant)
	if not workspace or not frappe.db.get_value("VerityAI Notification Setting", {"workspace": workspace}, "lead_notifications_enabled"):
		return []
	return send_notification(workspace, "New Lead", f"New lead: {doc.lead_name}", f"A new lead was captured from {doc.source_channel or 'your assistant'}. Open VerityAI to review it.", "AI Lead", doc.name)


def send_handoff_notification(doc, method=None):
	if doc.status != "Human Handoff":
		return []
	workspace = workspace_for_tenant(doc.tenant)
	if not workspace or frappe.db.exists("VerityAI Email Delivery Log", {"workspace": workspace, "notification_type": "Human Handoff", "reference_name": doc.name}):
		return []
	if not frappe.db.get_value("VerityAI Notification Setting", {"workspace": workspace}, "human_handoff_alerts_enabled"):
		return []
	return send_notification(workspace, "Human Handoff", "A conversation needs human help", "A customer conversation requested human assistance.", "AI Chat Session", doc.name)

def send_quote_request_notification(doc, method=None):
	if doc.status != "Pending":
		return []
	workspace = workspace_for_tenant(doc.tenant)
	if not workspace or frappe.db.exists("VerityAI Email Delivery Log", {"workspace": workspace, "notification_type": "Quotation Request", "reference_name": doc.name}):
		return []
	if not frappe.db.get_value("VerityAI Notification Setting", {"workspace": workspace}, "quote_request_alerts_enabled"):
		return []
	customer = doc.customer_name or "a customer"
	total = doc.estimated_total if doc.estimated_total is not None else "Not set"
	return send_notification(workspace, "Quotation Request", f"Quotation request {doc.name} needs approval", f"A quotation request for {customer} is ready for review. Estimated total: {total}. Open VerityAI to approve or reject it.", "AI Quotation Request", doc.name)


def send_provider_failure_notification(doc, method=None):
	if doc.alert_type != "System" or doc.status != "Open":
		return []
	workspace = workspace_for_tenant(doc.tenant)
	if not workspace or frappe.db.exists("VerityAI Email Delivery Log", {"workspace": workspace, "notification_type": "Provider Failure", "reference_name": doc.name}):
		return []
	if not frappe.db.get_value("VerityAI Notification Setting", {"workspace": workspace}, "provider_failure_alerts_enabled"):
		return []
	summary = doc.summary or "An AI provider requires attention."
	return send_notification(workspace, "Provider Failure", "VerityAI provider alert", summary, "AI Monitoring Alert", doc.name)


def send_usage_warning(workspace_name):
	wallet = frappe.db.get_value("VerityAI Usage Wallet", {"workspace": workspace_name}, ["name", "tokens_used", "tokens_remaining", "status"], as_dict=True)
	if not wallet or wallet.status not in {"Warning", "Exhausted"}:
		return []
	return send_notification(workspace_name, "Usage Warning", "VerityAI usage warning", f"Tokens used: {wallet.tokens_used}. Tokens remaining: {wallet.tokens_remaining}.", "VerityAI Usage Wallet", wallet.name)


def send_usage_warnings():
	for workspace in frappe.get_all("VerityAI Notification Setting", filters={"usage_warning_alerts_enabled": 1, "status": "Active"}, pluck="workspace"):
		try:
			send_usage_warning(workspace)
		except Exception:
			frappe.log_error(title=f"VerityAI Usage Warning: {workspace}", message=frappe.get_traceback())
	frappe.db.commit()


def send_daily_summary(workspace_name):
	workspace = frappe.get_doc("VerityAI Workspace", workspace_name)
	count = frappe.db.count("AI Lead", {"tenant": workspace.engine_tenant, "creation": [">=", frappe.utils.today()]})
	return send_notification(workspace_name, "Daily Lead Summary", "Your daily VerityAI lead summary", f"Your assistant captured {count} lead(s) today.")


def send_daily_summaries():
	for workspace in frappe.get_all("VerityAI Notification Setting", filters={"daily_summary_enabled": 1, "status": "Active"}, pluck="workspace"):
		try:
			send_daily_summary(workspace)
		except Exception:
			frappe.log_error(title=f"VerityAI Daily Summary: {workspace}", message=frappe.get_traceback())
	frappe.db.commit()

