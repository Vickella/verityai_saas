import frappe

from verityai_saas.api._response import endpoint, json_value
from verityai_saas.services.permissions import get_user_workspaces, require_workspace_permission
from verityai_saas.services.workspace import add_member, list_members, workspace_summary


@frappe.whitelist()
@endpoint
def list_workspaces():
	names = get_user_workspaces()
	return frappe.get_all("VerityAI Workspace", filters={"name": ["in", names]}, fields=["name", "workspace_name", "business_name", "status", "setup_progress", "engine_tenant"], order_by="workspace_name asc")


@frappe.whitelist()
@endpoint
def get(workspace):
	return workspace_summary(workspace)


@frappe.whitelist()
@endpoint
def members(workspace):
	require_workspace_permission(workspace, "manage_team")
	return list_members(workspace)


@frappe.whitelist()
@endpoint
def invite(workspace, email, role="Viewer"):
	require_workspace_permission(workspace, "manage_team")
	return {"member": add_member(workspace, email, role)}

