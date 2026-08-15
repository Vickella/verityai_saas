import frappe
from frappe.sessions import get_csrf_token

from verityai_saas import __version__


def get_context(context):
	if frappe.session.user != "Guest":
		frappe.local.flags.redirect_location = "/verityai"
		raise frappe.Redirect
	context.no_cache = 1
	context.title = "Sign in to VerityAI"
	context.csrf_token = get_csrf_token()
	context.asset_version = __version__
	return context
