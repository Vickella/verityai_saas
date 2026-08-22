import frappe


def execute():
	from verityai_saas.setup_doctypes import ensure_doctypes, ensure_default_plan
	from verityai_saas.services.billing import apply_trial_allowance_limit

	ensure_doctypes()
	ensure_default_plan()
	apply_trial_allowance_limit(5000)
	frappe.clear_cache()
