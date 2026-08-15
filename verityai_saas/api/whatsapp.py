import frappe

from verityai_saas.api._response import endpoint, json_value
from verityai_saas.services import whatsapp
from verityai_saas.services.admin_reauth import require_admin_reauthentication
from verityai_saas.services.onboarding import set_step
from verityai_saas.services.permissions import check_workspace_access, get_user_workspaces, is_operator, require_workspace_permission


@frappe.whitelist()
@endpoint
def get(workspace):
	check_workspace_access(workspace)
	return whatsapp.safe_setup(workspace)


@frappe.whitelist(methods=["POST"])
@endpoint
def update(workspace, values):
	require_workspace_permission(workspace, "manage_whatsapp")
	data = whatsapp.configure(workspace, json_value(values, {}))
	set_step(workspace, "whatsapp")
	return data



@frappe.whitelist(methods=["POST"])
@endpoint
def test_connection(workspace):
	if is_operator() and workspace not in get_user_workspaces():
		require_admin_reauthentication()
		check_workspace_access(workspace, allow_operator=True)
	else:
		require_workspace_permission(workspace, "manage_whatsapp")
	return whatsapp.test_connection(workspace)
