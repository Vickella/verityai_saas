import frappe

from verityai_saas.www.verityai._common import portal_context


def get_context(context):
	if frappe.session.user == "Guest":
		frappe.local.flags.redirect_location = "/verityai/signup"
		raise frappe.Redirect
	return portal_context(context, "dashboard")
