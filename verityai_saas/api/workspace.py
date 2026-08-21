import frappe

from verityai_saas.api._response import endpoint, json_value
from verityai_saas.services.permissions import get_user_workspaces, require_workspace_permission
from verityai_saas.services.workspace import (
	add_member,
	list_members,
	remove_member,
	resend_member_invitation,
	update_member,
	workspace_summary,
)


@frappe.whitelist()
@endpoint
def list_workspaces(workspace=None):
	"""Return one resolved customer workspace without exposing a tenant directory."""
	names = get_user_workspaces()
	if not names:
		return []
	if workspace and workspace in names:
		selected = workspace
	else:
		default_workspaces = frappe.get_all(
			"VerityAI Account",
			filters={"default_workspace": ["in", names]},
			pluck="default_workspace",
			order_by="modified desc",
		)
		selected = default_workspaces[0] if default_workspaces else names[0]
	return frappe.get_all(
		"VerityAI Workspace",
		filters={"name": selected},
		fields=["name", "workspace_name", "business_name", "status", "setup_progress", "engine_tenant"],
		limit=1,
	)


@frappe.whitelist()
@endpoint
def get(workspace):
	return workspace_summary(workspace)


@frappe.whitelist()
@endpoint
def members(workspace):
	require_workspace_permission(workspace, "manage_team")
	return list_members(workspace)


@frappe.whitelist(methods=["POST"])
@endpoint
def invite(workspace, email, role="Viewer"):
	require_workspace_permission(workspace, "manage_team")
	return {"member": add_member(workspace, email, role)}


@frappe.whitelist(methods=["POST"])
@endpoint
def resend_invite(workspace, member):
	require_workspace_permission(workspace, "manage_team")
	return {"member": resend_member_invitation(workspace, member)}


@frappe.whitelist(methods=["POST"])
@endpoint
def update(workspace, member, role=None, permissions=None):
	require_workspace_permission(workspace, "manage_team")
	return {
		"member": update_member(
			workspace,
			member,
			role=role,
			permissions=json_value(permissions, {}),
		)
	}


@frappe.whitelist(methods=["POST"])
@endpoint
def remove(workspace, member):
	require_workspace_permission(workspace, "manage_team")
	return {"member": remove_member(workspace, member)}
