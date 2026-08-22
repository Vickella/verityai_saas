import frappe


CONNECTOR_ROLES = {"System Manager", "Verity AI Administrator"}


def _require_connector_user():
	user = frappe.session.user
	if user == "Guest":
		frappe.throw("Authentication is required.", frappe.PermissionError)
	if not CONNECTOR_ROLES.intersection(set(frappe.get_roles(user))):
		frappe.throw("You do not have permission to use the ERPNext connector.", frappe.PermissionError)
	if frappe.db.get_value("User", user, "user_type") != "System User":
		frappe.throw("The ERPNext connector requires a system user.", frappe.PermissionError)
	return user


@frappe.whitelist()
def health():
	"""Verify an authenticated, role-scoped VerityAI connector installation.

	This intentionally exposes no Python, shell, SQL, Bench console or arbitrary
	script execution endpoint. Operational actions remain governed by Frappe
	permissions and the existing VerityAI action approval controls.
	"""
	user = _require_connector_user()
	installed_apps = set(frappe.get_installed_apps())
	return {
		"connector": True,
		"version": frappe.get_attr("verity_ai.__version__"),
		"user": user,
		"erpnext_installed": "erpnext" in installed_apps,
		"capabilities": [
			"authenticated_desk_assistant",
			"permission_scoped_records",
			"reports_and_exports",
			"approval_controlled_actions",
			"read_only_diagnostics",
		],
		"arbitrary_script_execution": False,
	}
