from urllib.parse import urlencode

import frappe
from frappe import _
from frappe.core.doctype.user.user import sign_up
from frappe.utils import validate_email_address

from verityai_saas.api._response import endpoint


@frappe.whitelist(allow_guest=True, methods=["POST"])
@endpoint
def register(email, full_name, business_name, workspace_name=None, account_name=None):
	email = _required(email, _("Email"), 140).lower()
	if not validate_email_address(email):
		frappe.throw(_("Please enter a valid email address."), frappe.ValidationError)
	full_name = _required(full_name, _("Full name"), 120)
	business_name = _required(business_name, _("Business name"), 140)
	workspace_name = _required(workspace_name or business_name, _("Workspace name"), 140)
	account_name = _required(account_name or business_name, _("Account name"), 140)
	query = urlencode(
		{
			"account_name": account_name,
			"workspace_name": workspace_name,
			"business_name": business_name,
		}
	)
	redirect_to = f"/verityai/onboarding?{query}"
	status, message = sign_up(email, full_name, redirect_to)
	login_url = "/login?" + urlencode({"redirect-to": redirect_to})
	return {
		"registered": bool(status),
		"registration_status": status,
		"message": message,
		"login_url": login_url,
	}


def _required(value, label, max_length):
	value = str(value or "").strip()
	if not value:
		frappe.throw(_("{0} is required.").format(label), frappe.ValidationError)
	if len(value) > max_length:
		frappe.throw(_("{0} must be {1} characters or fewer.").format(label, max_length), frappe.ValidationError)
	return value
