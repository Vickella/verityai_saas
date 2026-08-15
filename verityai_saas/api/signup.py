from urllib.parse import urlencode

import frappe
from frappe import _
from frappe.rate_limiter import rate_limit
from frappe.utils import cint, escape_html, validate_email_address

from verityai_saas.api._response import endpoint


@frappe.whitelist(allow_guest=True, methods=["POST"])
@endpoint
@rate_limit(key="verityai_customer_signup", limit=10, seconds=60 * 60, methods=["POST"], ip_based=True)
def register(email, full_name, business_name, password, confirm_password=None, workspace_name=None, account_name=None):
	email = _required(email, _("Email"), 140).lower()
	if not validate_email_address(email):
		frappe.throw(_("Please enter a valid email address."), frappe.ValidationError)
	full_name = _required(full_name, _("Full name"), 120)
	business_name = _required(business_name, _("Business name"), 140)
	workspace_name = _required(workspace_name or business_name, _("Workspace name"), 140)
	account_name = _required(account_name or business_name, _("Account name"), 140)
	password = _required(password, _("Password"), 128)
	if len(password) < 8:
		frappe.throw(_("Password must be at least 8 characters."), frappe.ValidationError)
	if password != str(confirm_password or ""):
		frappe.throw(_("Passwords do not match."), frappe.ValidationError)
	if frappe.db.exists("User", email):
		frappe.throw(_("An account already exists for this email. Please sign in instead."), frappe.ValidationError)

	max_signups = cint(frappe.get_system_settings("max_signups_allowed_per_hour") or 50)
	if frappe.db.get_creation_count("User", 60) >= max_signups:
		frappe.local.response["http_status_code"] = 429
		frappe.throw(_("Too many accounts were created recently. Please try again later."), frappe.ValidationError)
	query = urlencode(
		{
			"account_name": account_name,
			"workspace_name": workspace_name,
			"business_name": business_name,
		}
	)
	redirect_to = f"/verityai/onboarding?{query}"
	parts = full_name.split(None, 1)
	savepoint = f"verityai_signup_{frappe.generate_hash(length=8)}"
	frappe.db.savepoint(savepoint)
	try:
		user = frappe.get_doc(
			{
				"doctype": "User",
				"email": email,
				"first_name": escape_html(parts[0]),
				"last_name": escape_html(parts[1]) if len(parts) > 1 else "",
				"enabled": 1,
				"user_type": "Website User",
				"new_password": password,
				"send_welcome_email": 0,
			}
		)
		user.flags.ignore_permissions = True
		user.insert()
		frappe.cache.hset("redirect_after_login", user.name, redirect_to)
		frappe.local.login_manager.authenticate(user=email, pwd=password)
		frappe.local.login_manager.post_login()
	except Exception:
		frappe.db.rollback(save_point=savepoint)
		raise
	login_url = "/verityai/signin?" + urlencode({"redirect-to": redirect_to})
	return {
		"registered": True,
		"authenticated": frappe.session.user == email,
		"registration_status": 1,
		"message": _("Your account is ready. Continue to create your secure workspace."),
		"login_url": login_url,
		"next_url": redirect_to,
	}


def _required(value, label, max_length):
	value = str(value or "").strip()
	if not value:
		frappe.throw(_("{0} is required.").format(label), frappe.ValidationError)
	if len(value) > max_length:
		frappe.throw(_("{0} must be {1} characters or fewer.").format(label, max_length), frappe.ValidationError)
	return value
