import frappe


WORKSPACE_TO_FRAPPE_ROLE = {
	"Owner": "VerityAI Customer Owner",
	"Admin": "VerityAI Customer Admin",
	"Sales": "VerityAI Sales User",
	"Support": "VerityAI Support User",
	"Billing Manager": "VerityAI Billing User",
	"Viewer": "VerityAI Viewer",
}
CUSTOMER_ROLES = set(WORKSPACE_TO_FRAPPE_ROLE.values())


def assign_workspace_role(user, workspace_role):
	role = WORKSPACE_TO_FRAPPE_ROLE.get(workspace_role)
	if not role or not frappe.db.exists("User", user):
		return None
	if role not in frappe.get_roles(user):
		frappe.get_doc("User", user).add_roles(role)
	return role


def sync_workspace_roles(user):
	if not frappe.db.exists("User", user):
		return []
	workspace_roles = frappe.get_all(
		"VerityAI Workspace Member",
		filters={"user": user, "status": "Active"},
		pluck="workspace_role",
	)
	if frappe.db.exists("VerityAI Workspace", {"owner_user": user}):
		workspace_roles.append("Owner")
	required = {
		WORKSPACE_TO_FRAPPE_ROLE[role]
		for role in workspace_roles
		if role in WORKSPACE_TO_FRAPPE_ROLE
	}
	current = set(frappe.get_roles(user))
	doc = frappe.get_doc("User", user)
	missing = sorted(required - current)
	obsolete = sorted((current & CUSTOMER_ROLES) - required)
	if missing:
		doc.add_roles(*missing)
	if obsolete:
		doc.remove_roles(*obsolete)
	return sorted(required)
