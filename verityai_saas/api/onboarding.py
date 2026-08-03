import frappe

from verityai_saas.api._response import endpoint, json_value
from verityai_saas.services.onboarding import create_workspace, set_step
from verityai_saas.services.permissions import check_workspace_access, is_operator, require_login


@frappe.whitelist()
@endpoint
def create(account_name, workspace_name, business_name=None, owner_user=None, plan=None, values=None):
	user = require_login()
	owner = owner_user if owner_user and is_operator(user) else user
	return create_workspace(owner, account_name, workspace_name, business_name, plan, json_value(values, {}))


@frappe.whitelist()
@endpoint
def update_step(workspace, step_code, status="Done"):
	check_workspace_access(workspace)
	return {"setup_progress": set_step(workspace, step_code, status)}

