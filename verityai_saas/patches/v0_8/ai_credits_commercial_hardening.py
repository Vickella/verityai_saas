import frappe

from verityai_saas.services.engine import MODEL_COSTS_PER_1K
from verityai_saas.setup_doctypes import install


def execute():
	"""Install commercial doctypes, seed public plans, and restore trusted cost rates."""
	install()
	if not frappe.db.exists("DocType", "AI Configuration"):
		return
	meta = frappe.get_meta("AI Configuration")
	if not meta.has_field("prompt_cost_per_1k") or not meta.has_field("completion_cost_per_1k"):
		return
	for row in frappe.get_all("AI Configuration", fields=["name", "model_name"]):
		costs = MODEL_COSTS_PER_1K.get(row.model_name)
		if costs:
			frappe.db.set_value(
				"AI Configuration", row.name,
				{"prompt_cost_per_1k": costs[0], "completion_cost_per_1k": costs[1]},
				update_modified=False,
			)
