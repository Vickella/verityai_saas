import frappe


WORKSPACE_TO_FRAPPE_ROLE = {
	"Owner": "VerityAI Customer Owner",
	"Admin": "VerityAI Customer Admin",
	"Sales": "VerityAI Sales User",
	"Support": "VerityAI Support User",
	"Billing Manager": "VerityAI Billing User",
	"Viewer": "VerityAI Viewer",
}


def assign_workspace_role(user, workspace_role):
	role = WORKSPACE_TO_FRAPPE_ROLE.get(workspace_role)
	if not role or not frappe.db.exists("User", user):
		return None
	if role not in frappe.get_roles(user):
		frappe.get_doc("User", user).add_roles(role)
	return role

