from frappe.sessions import get_csrf_token

from verityai_saas import __version__


def get_context(context):
	context.no_cache = 1
	context.title = "Website Doctor report · VerityAI"
	context.csrf_token = get_csrf_token()
	context.asset_version = __version__
	return context
