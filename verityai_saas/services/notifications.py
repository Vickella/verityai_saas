from email.message import EmailMessage
from html import escape
import smtplib
import ssl

import frappe
from frappe.utils import cint, now_datetime

from verityai_saas.services.entitlements import email_delivery_allowance, feature_allowed, workspace_context


def workspace_for_tenant(tenant):
	return frappe.db.get_value("VerityAI Workspace", {"engine_tenant": tenant}, "name")

def _deliver_email(workspace_name, setting, recipient, subject, message):
	context = workspace_context(workspace_name=workspace_name)
	if setting.custom_smtp_enabled and feature_allowed(context, "can_use_custom_smtp"):
		from verityai_saas.services.integrations import _smtp_host
		host = _smtp_host(setting.smtp_host)
		port = int(setting.smtp_port or 587)
		if port not in {465, 587}:
			frappe.throw("SMTP port must be 465 or 587.", frappe.ValidationError)
		sender = setting.smtp_sender_email or setting.notification_email
		password = setting.get_password("smtp_password", raise_exception=False)
		if not sender or not setting.smtp_username or not password:
			frappe.throw("Custom SMTP credentials are incomplete.", frappe.ValidationError)
		email = EmailMessage()
		email["From"] = sender
		email["To"] = recipient
		email["Subject"] = subject
		if setting.reply_to_email:
			email["Reply-To"] = setting.reply_to_email
		email.set_content("This message requires an HTML-capable email client.")
		email.add_alternative(message, subtype="html")
		context_ssl = ssl.create_default_context()
		if port == 465:
			with smtplib.SMTP_SSL(host, port, timeout=15, context=context_ssl) as client:
				client.login(setting.smtp_username, password)
				client.send_message(email)
		else:
			with smtplib.SMTP(host, port, timeout=15) as client:
				client.ehlo()
				client.starttls(context=context_ssl)
				client.ehlo()
				client.login(setting.smtp_username, password)
				client.send_message(email)
		return
	frappe.sendmail(recipients=[recipient], subject=subject, message=message, reply_to=setting.reply_to_email or None)

def recipients(setting):
	values = [setting.notification_email] + (setting.alert_recipients or "").replace(";", ",").split(",")
	return sorted({value.strip() for value in values if value and value.strip()})


def send_notification(workspace_name, notification_type, subject, message, reference_doctype=None, reference_name=None):
	allowance = email_delivery_allowance(workspace_name)
	if allowance == 0:
		return []
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
	recipient_values = recipients(setting)
	if allowance is not None:
		recipient_values = recipient_values[:allowance]
	logs = []
	for recipient in recipient_values:
		log = frappe.get_doc({"doctype": "VerityAI Email Delivery Log", "workspace": workspace_name, "notification_type": notification_type, "recipient": recipient, "subject": subject, "message": email_body, "status": "Pending", "reference_doctype": reference_doctype, "reference_name": reference_name}).insert(ignore_permissions=True)
		try:
			_deliver_email(workspace_name, setting, recipient, subject, email_body)
			log.status, log.sent_on = "Sent", now_datetime()
		except Exception as exc:
			log.status, log.error = "Failed", str(exc)[:500]
		log.save(ignore_permissions=True)
		logs.append(log.name)
	if logs:
		wallet = frappe.db.get_value("VerityAI Usage Wallet", {"workspace": workspace_name}, "name")
		if wallet:
			period_start = frappe.db.get_value("VerityAI Usage Wallet", wallet, "period_start")
			sent = frappe.db.count("VerityAI Email Delivery Log", {
				"workspace": workspace_name,
				"status": "Sent",
				"creation": [">=", period_start],
			})
			frappe.db.set_value("VerityAI Usage Wallet", wallet, "email_sends_used", sent)
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
	wallet = frappe.db.get_value(
		"VerityAI Usage Wallet", {"workspace": workspace_name},
		["name", "opening_token_allowance", "top_up_tokens", "promotional_credits", "tokens_used", "tokens_remaining", "status", "period_start"],
		as_dict=True,
	)
	if not wallet:
		return []
	total = cint(wallet.opening_token_allowance) + cint(wallet.top_up_tokens) + cint(wallet.promotional_credits)
	percent = round((cint(wallet.tokens_used) / max(total, 1)) * 100)
	threshold = 100 if percent >= 100 else 85 if percent >= 85 else 70 if percent >= 70 else 0
	if not threshold:
		return []
	reference = f"{wallet.name}:{wallet.period_start}:{threshold}"
	notification_type = f"AI Credits {threshold}%"
	if frappe.db.exists("VerityAI Email Delivery Log", {"workspace": workspace_name, "notification_type": notification_type, "reference_name": reference}):
		return []
	subject = "Your VerityAI assistant is paused" if threshold == 100 else f"You have used {threshold}% of your AI credits"
	message = (
		f"AI credits used: {cint(wallet.tokens_used):,}. AI credits remaining: {cint(wallet.tokens_remaining):,}. "
		+ ("Purchase a plan or additional credits to resume AI responses." if threshold == 100 else "Review usage or add prepaid credits before service is interrupted.")
	)
	return send_notification(workspace_name, notification_type, subject, message, "VerityAI Usage Wallet", reference)


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



def retry_failed_delivery(workspace_name, delivery_log):
	allowance = email_delivery_allowance(workspace_name)
	if allowance == 0:
		frappe.throw("The email allowance for this workspace has been reached.", frappe.PermissionError)
	if not frappe.db.exists("VerityAI Email Delivery Log", {"name": delivery_log, "workspace": workspace_name}):
		frappe.throw("Email delivery log was not found.", frappe.DoesNotExistError)
	log = frappe.get_doc("VerityAI Email Delivery Log", delivery_log)
	if log.status != "Failed":
		frappe.throw("Only failed email deliveries can be retried.", frappe.ValidationError)
	setting_name = frappe.db.get_value("VerityAI Notification Setting", {"workspace": workspace_name, "status": "Active"}, "name")
	if not setting_name:
		frappe.throw("Active email notification settings are required.", frappe.ValidationError)
	setting = frappe.get_doc("VerityAI Notification Setting", setting_name)
	try:
		_deliver_email(
			workspace_name, setting, log.recipient, log.subject,
			log.message or "This VerityAI notification is being retried after an earlier delivery failure.",
		)
		log.status = "Sent"
		log.sent_on = now_datetime()
		log.error = None
	except Exception as exc:
		log.error = str(exc)[:500]
		log.save(ignore_permissions=True)
		raise
	log.save(ignore_permissions=True)
	wallet = frappe.db.get_value("VerityAI Usage Wallet", {"workspace": workspace_name}, ["name", "period_start"], as_dict=True)
	if wallet:
		sent = frappe.db.count("VerityAI Email Delivery Log", {
			"workspace": workspace_name, "status": "Sent", "creation": [">=", wallet.period_start],
		})
		frappe.db.set_value("VerityAI Usage Wallet", wallet.name, "email_sends_used", sent)
	return {"delivery_log": log.name, "status": log.status, "sent_on": log.sent_on}
