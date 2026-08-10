import frappe
from frappe.sessions import get_csrf_token

from verityai_saas import __version__


def portal_context(context, page):
	if frappe.session.user == "Guest":
		frappe.local.flags.redirect_location = "/login?redirect-to=/verityai"
		raise frappe.Redirect
	context.no_cache = 1
	context.title = f"VerityAI · {page.replace('_', ' ').title()}"
	context.portal_page = page
	context.user_email = frappe.session.user
	context.csrf_token = get_csrf_token()
	context.asset_version = __version__
	return context
