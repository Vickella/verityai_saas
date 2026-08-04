import frappe

from verityai_saas.api._response import endpoint, json_value
from verityai_saas.services import integrations
from verityai_saas.services.permissions import check_workspace_access, require_workspace_permission


@frappe.whitelist()
@endpoint
def get(workspace):
	check_workspace_access(workspace)
	return integrations.integration_status(workspace)


@frappe.whitelist(methods=["POST"])
@endpoint
def update_provider(workspace, values):
	require_workspace_permission(workspace, "manage_assistant")
	return integrations.configure_provider(workspace, json_value(values, {}))


@frappe.whitelist(methods=["POST"])
@endpoint
def update_erpnext(workspace, values):
	require_workspace_permission(workspace, "manage_assistant")
	return integrations.configure_erpnext(workspace, json_value(values, {}))


@frappe.whitelist(methods=["POST"])
@endpoint
def update_smtp(workspace, values):
	require_workspace_permission(workspace, "manage_email")
	return integrations.configure_smtp(workspace, json_value(values, {}))


@frappe.whitelist(methods=["POST"])
@endpoint
def create_credential(workspace, label, scopes):
	require_workspace_permission(workspace, "manage_assistant")
	return integrations.create_api_credential(workspace, label, json_value(scopes, []))


@frappe.whitelist(methods=["POST"])
@endpoint
def revoke_credential(workspace, credential):
	require_workspace_permission(workspace, "manage_assistant")
	return integrations.revoke_api_credential(workspace, credential)