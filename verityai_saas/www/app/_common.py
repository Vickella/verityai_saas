import frappe


def portal_context(context, page):
	if frappe.session.user == "Guest":
		frappe.local.flags.redirect_location = "/login?redirect-to=/app"
		raise frappe.Redirect
	context.no_cache = 1
	context.title = f"VerityAI · {page.replace('_', ' ').title()}"
	context.portal_page = page
	context.user_email = frappe.session.user
	return context

