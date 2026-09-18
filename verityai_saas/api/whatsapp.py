import frappe

from verityai_saas.api._response import endpoint, json_value
from verityai_saas.services import setup_guide, whatsapp
from verityai_saas.services.admin_reauth import require_admin_reauthentication
from verityai_saas.services.onboarding import set_step
from verityai_saas.services.permissions import check_workspace_access, get_user_workspaces, is_operator, require_workspace_permission


@frappe.whitelist()
@endpoint
def get(workspace, account=None):
	check_workspace_access(workspace)
	accounts = whatsapp.list_accounts(workspace)
	data = whatsapp.safe_setup(workspace, account)
	data["accounts"] = accounts
	data["setup_guide"] = setup_guide.status()
	return data


@frappe.whitelist(methods=["POST"])
@endpoint
def update(workspace, values, account=None):
	require_workspace_permission(workspace, "manage_whatsapp")
	data = whatsapp.configure(workspace, json_value(values, {}), account=account)
	set_step(workspace, "whatsapp")
	return data


@frappe.whitelist(methods=["POST"])
@endpoint
def create(workspace, values):
	require_workspace_permission(workspace, "manage_whatsapp")
	data = whatsapp.create_account(workspace, json_value(values, {}))
	set_step(workspace, "whatsapp")
	return data


@frappe.whitelist(methods=["POST"])
@endpoint
def set_state(workspace, account, active=None, is_default=None):
	require_workspace_permission(workspace, "manage_whatsapp")
	return whatsapp.set_account_state(workspace, account, active=active, is_default=is_default)



@frappe.whitelist(methods=["POST"])
@endpoint
def test_connection(workspace, account=None):
	if is_operator() and workspace not in get_user_workspaces():
		require_admin_reauthentication()
		check_workspace_access(workspace, allow_operator=True)
	else:
		require_workspace_permission(workspace, "manage_whatsapp")
	return whatsapp.test_connection(workspace, account=account)


@frappe.whitelist(methods=["POST"])
@endpoint
def subscribe_waba(workspace, account=None):
	if is_operator() and workspace not in get_user_workspaces():
		require_admin_reauthentication()
		check_workspace_access(workspace, allow_operator=True)
	else:
		require_workspace_permission(workspace, "manage_whatsapp")
	return whatsapp.subscribe_waba(workspace, account=account)
