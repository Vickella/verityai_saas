from html import escape
import os

import frappe
from frappe.utils import cint, get_url, getdate, now_datetime, today


SUPPORT_EMAIL = "support@veritycore.co.zw"
SUPPORT_ACCOUNT_NAME = "VerityAI Support"
PASSWORD_RESET_TEMPLATE = "VerityAI Password Reset"
DEFAULT_SMTP_SERVER = "mail.veritycore.co.zw"
ALLOWED_SMTP_PORTS = {465, 587}


def _clean_text(value):
	return escape(str(value or "")).replace("\n", "<br>")


def _button(url, label):
	if not url:
		return ""
	return (
		'<p style="margin:28px 0 8px">'
		f'<a href="{escape(url, quote=True)}" style="display:inline-block;background:#1f6feb;color:#ffffff;'
		'padding:12px 20px;border-radius:8px;text-decoration:none;font-weight:700">'
		f"{escape(label)}</a></p>"
	)


def render_message(title, paragraphs, action_url=None, action_label=None, preheader=None):
	paragraph_html = "".join(
		f'<p style="margin:0 0 16px;color:#344054;font-size:15px;line-height:1.7">{_clean_text(value)}</p>'
		for value in paragraphs if value
	)
	return f"""
	<div style="display:none;max-height:0;overflow:hidden;color:transparent">{_clean_text(preheader or title)}</div>
	<table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background:#f4f7fb;padding:32px 12px;font-family:Arial,sans-serif">
		<tr><td align="center">
			<table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="max-width:620px;background:#ffffff;border:1px solid #e4e9f1;border-radius:14px;overflow:hidden">
				<tr><td style="background:#0b1f36;padding:24px 30px;color:#ffffff;font-size:22px;font-weight:800">VerityAI</td></tr>
				<tr><td style="padding:34px 30px 26px">
					<h1 style="margin:0 0 20px;color:#101828;font-size:26px;line-height:1.25">{escape(title)}</h1>
					{paragraph_html}
					{_button(action_url, action_label or "Open VerityAI")}
				</td></tr>
				<tr><td style="border-top:1px solid #e4e9f1;padding:20px 30px;color:#667085;font-size:12px;line-height:1.6">
					This is an account message from VerityAI. Contact support@veritycore.co.zw if you need assistance.
				</td></tr>
			</table>
		</td></tr>
	</table>
	"""


def ensure_system_email_templates():
	"""Install the branded template while retaining Frappe's secure reset key flow."""
	response = render_message(
		"Reset your password",
		[
			"Hello {{ first_name }},",
			"We received a request to reset the password for your VerityAI account.",
			"Use the button below to choose a new password. If you did not make this request, you can safely ignore this message.",
		],
		"{{ link }}",
		"Reset password",
		"Securely reset your VerityAI password.",
	)
	values = {
		"subject": "Reset your VerityAI password",
		"use_html": 1,
		"response_html": response,
		"response": "",
	}
	if frappe.db.exists("Email Template", PASSWORD_RESET_TEMPLATE):
		frappe.db.set_value("Email Template", PASSWORD_RESET_TEMPLATE, values, update_modified=False)
	else:
		frappe.get_doc({"doctype": "Email Template", "name": PASSWORD_RESET_TEMPLATE, **values}).insert(
			ignore_permissions=True
		)
	if frappe.get_meta("System Settings").has_field("reset_password_template"):
		frappe.db.set_single_value("System Settings", "reset_password_template", PASSWORD_RESET_TEMPLATE)


def email_configuration_status():
	name = frappe.db.get_value("Email Account", {"email_id": SUPPORT_EMAIL}, "name")
	if not name:
		return {
			"configured": False,
			"email_id": SUPPORT_EMAIL,
			"smtp_server": DEFAULT_SMTP_SERVER,
			"smtp_port": 465,
			"use_tls": False,
			"use_ssl": True,
			"password_present": False,
		}
	doc = frappe.get_doc("Email Account", name)
	return {
		"configured": bool(doc.enable_outgoing and doc.default_outgoing and doc.smtp_server),
		"email_id": doc.email_id,
		"smtp_server": doc.smtp_server,
		"smtp_port": cint(doc.smtp_port),
		"use_tls": bool(doc.use_tls),
		"use_ssl": bool(doc.use_ssl_for_outgoing),
		"password_present": bool(doc.get_password("password", raise_exception=False)),
	}


def configure_support_email(values):
	from verityai_saas.services.integrations import _smtp_host

	values = values or {}
	host = _smtp_host(values.get("smtp_server") or DEFAULT_SMTP_SERVER)
	port = cint(values.get("smtp_port") or 465)
	if port not in ALLOWED_SMTP_PORTS:
		frappe.throw("SMTP port must be 465 or 587.", frappe.ValidationError)
	use_ssl = port == 465
	use_tls = port == 587
	name = frappe.db.get_value("Email Account", {"email_id": SUPPORT_EMAIL}, "name")
	doc = frappe.get_doc("Email Account", name) if name else frappe.get_doc({"doctype": "Email Account"})
	doc.update(
		{
			"email_account_name": doc.email_account_name or SUPPORT_ACCOUNT_NAME,
			"email_id": SUPPORT_EMAIL,
			"auth_method": "Basic",
			"enable_incoming": 0,
			"enable_outgoing": 1,
			"default_outgoing": 1,
			"smtp_server": host,
			"smtp_port": str(port),
			"use_tls": int(use_tls),
			"use_ssl_for_outgoing": int(use_ssl),
			"always_use_account_email_id_as_sender": 1,
			"always_use_account_name_as_sender_name": 1,
			"send_unsubscribe_message": 0,
			"track_email_status": 1,
			"no_smtp_authentication": 0,
			"awaiting_password": 0,
		}
	)
	password = str(values.get("password") or "")
	if password:
		doc.password = password
	elif not name or not doc.get_password("password", raise_exception=False):
		frappe.throw("The support mailbox password is required.", frappe.ValidationError)
	doc.flags.ignore_permissions = True
	if doc.is_new():
		doc.insert()
	else:
		doc.save()
	ensure_system_email_templates()
	return email_configuration_status()


def configure_support_email_from_environment():
	"""Deployment helper that keeps the mailbox password out of command arguments and logs."""
	password = os.environ.pop("VERITYAI_SUPPORT_EMAIL_PASSWORD", "")
	if not password:
		frappe.throw("VERITYAI_SUPPORT_EMAIL_PASSWORD is required.", frappe.ValidationError)
	return configure_support_email({"password": password})


def email_credential_security_status():
	name = frappe.db.get_value("Email Account", {"email_id": SUPPORT_EMAIL}, "name")
	return {
		"account": name,
		"encrypted_record_present": bool(
			name
			and frappe.db.exists(
				"__Auth",
				{"doctype": "Email Account", "name": name, "fieldname": "password", "encrypted": 1},
			)
		),
		"password_returned_by_status_api": False,
	}


def send_support_test_email():
	message = render_message(
		"Email delivery is ready",
		[
			"The VerityAI support mailbox has been connected successfully.",
			"Password reset, account, billing, trial and AI credit messages can now be delivered from this address.",
		],
		get_url("/verityai/admin"),
		"Open operator console",
	)
	frappe.sendmail(
		recipients=[SUPPORT_EMAIL],
		sender=f"VerityAI Support <{SUPPORT_EMAIL}>",
		reply_to=SUPPORT_EMAIL,
		subject="VerityAI email delivery is ready",
		message=message,
		delayed=False,
	)
	return {"sent": True, "recipient": SUPPORT_EMAIL}


def _billing_recipient(workspace_name):
	account = frappe.db.get_value("VerityAI Workspace", workspace_name, "account")
	return frappe.db.get_value("VerityAI Account", account, "billing_email") if account else None


def send_transactional(
	workspace_name,
	notification_type,
	subject,
	title,
	paragraphs,
	reference_doctype=None,
	reference_name=None,
	action_url=None,
	action_label=None,
	recipient=None,
):
	recipient = recipient or _billing_recipient(workspace_name)
	if not recipient:
		return []
	if reference_name and frappe.db.exists(
		"VerityAI Email Delivery Log",
		{"workspace": workspace_name, "notification_type": notification_type, "reference_name": reference_name},
	):
		return []
	message = render_message(title, paragraphs, action_url, action_label)
	log = frappe.get_doc(
		{
			"doctype": "VerityAI Email Delivery Log",
			"workspace": workspace_name,
			"notification_type": notification_type,
			"recipient": recipient,
			"subject": subject,
			"message": message,
			"status": "Pending",
			"reference_doctype": reference_doctype,
			"reference_name": reference_name,
		}
	).insert(ignore_permissions=True)
	try:
		frappe.sendmail(
			recipients=[recipient],
			sender=f"VerityAI Support <{SUPPORT_EMAIL}>",
			reply_to=SUPPORT_EMAIL,
			subject=subject,
			message=message,
		)
		log.status = "Sent"
		log.sent_on = now_datetime()
	except Exception as exc:
		log.status = "Failed"
		log.error = str(exc)[:500]
	log.save(ignore_permissions=True)
	return [log.name]


def send_workspace_welcome(workspace_name):
	workspace = frappe.get_doc("VerityAI Workspace", workspace_name)
	return send_transactional(
		workspace_name,
		"Workspace Welcome",
		"Welcome to VerityAI",
		f"Welcome to {workspace.business_name or workspace.workspace_name}",
		[
			"Your secure VerityAI workspace is ready.",
			"Complete the guided setup to shape your assistant, add trusted knowledge and prepare your website experience.",
		],
		"VerityAI Workspace",
		workspace.name,
		get_url(f"/verityai/assistant?workspace={workspace.name}&guided=1"),
		"Continue setup",
	)


def queue_workspace_welcome(workspace_name):
	if getattr(frappe.flags, "in_test", False):
		return
	frappe.enqueue(
		"verityai_saas.services.platform_email.send_workspace_welcome",
		workspace_name=workspace_name,
		queue="short",
		enqueue_after_commit=True,
	)


def send_trial_lifecycle_emails():
	current_date = getdate(today())
	for row in frappe.get_all(
		"VerityAI Subscription",
		filters={"status": "Trial"},
		fields=["name", "workspace", "trial_end"],
	):
		if not row.trial_end:
			continue
		days_left = (getdate(row.trial_end) - current_date).days
		if days_left not in {7, 3, 1, 0}:
			continue
		when = "today" if days_left == 0 else "tomorrow" if days_left == 1 else f"in {days_left} days"
		reference = f"{row.name}:trial:{days_left}"
		send_transactional(
			row.workspace,
			f"Trial Ending {days_left}",
			"Your VerityAI trial is ending soon",
			f"Your trial ends {when}",
			[
				f"Your VerityAI trial ends {when}.",
				"Choose a plan to keep your assistant available and preserve uninterrupted customer conversations.",
			],
			"VerityAI Subscription",
			reference,
			get_url(f"/verityai/billing?workspace={row.workspace}"),
			"Choose a plan",
		)
	frappe.db.commit()


def send_trial_expired(workspace_name, subscription_name):
	return send_transactional(
		workspace_name,
		"Trial Expired",
		"Your VerityAI trial has ended",
		"Your trial has ended",
		[
			"Your assistant is now paused because the free trial has ended.",
			"Your workspace and settings remain secure. Choose a plan whenever you are ready to restore AI responses.",
		],
		"VerityAI Subscription",
		f"{subscription_name}:expired",
		get_url(f"/verityai/billing?workspace={workspace_name}"),
		"Restore your assistant",
	)


def send_payment_confirmation(workspace_name, billing_event):
	event = frappe.get_doc("VerityAI Billing Event", billing_event)
	return send_transactional(
		workspace_name,
		"Payment Confirmation",
		"Your VerityAI payment is confirmed",
		"Payment confirmed",
		[
			f"We received your payment of {event.currency or 'USD'} {float(event.amount or 0):,.2f}.",
			"Your billing record is available in your workspace.",
		],
		"VerityAI Billing Event",
		f"{event.name}:confirmed",
		get_url(f"/verityai/billing?workspace={workspace_name}"),
		"View billing",
	)
