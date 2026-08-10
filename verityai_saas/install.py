import frappe
from frappe import _


REQUIRED_ENGINE_DOCTYPES = (
	"AI Tenant",
	"AI Configuration",
	"AI Chat Session",
	"AI Lead",
	"AI Usage Log",
)


def validate_engine_installation():
	"""Validate the local engine without invoking Frappe's remote dependency resolver."""
	missing = [name for name in REQUIRED_ENGINE_DOCTYPES if not frappe.db.exists("DocType", name)]
	if missing:
		frappe.throw(
			_("Install and initialize verity_ai before verityai_saas. Missing engine DocTypes: {0}").format(
				", ".join(missing)
			),
			frappe.ValidationError,
		)
	return True
