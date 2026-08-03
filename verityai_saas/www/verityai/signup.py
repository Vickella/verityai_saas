import frappe


def get_context(context):
	if frappe.session.user != "Guest":
		frappe.local.flags.redirect_location = "/verityai/onboarding"
		raise frappe.Redirect
	context.no_cache = 1
	context.title = "Create your VerityAI account"
	return context
