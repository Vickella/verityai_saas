import frappe

from verityai_saas.services.user_roles import assign_workspace_role


def execute():
	if not frappe.db.exists("DocType", "VerityAI Workspace Member"):
		return
	for member in frappe.get_all(
		"VerityAI Workspace Member",
		filters={"status": "Active"},
		fields=["user", "workspace_role"],
	):
		assign_workspace_role(member.user, member.workspace_role)

