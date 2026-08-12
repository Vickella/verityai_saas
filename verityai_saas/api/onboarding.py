import frappe

from verityai_saas.api._response import endpoint, json_value
from verityai_saas.services.onboarding import complete_setup, create_workspace, set_step
from verityai_saas.services.permissions import check_workspace_access, is_operator, require_login


@frappe.whitelist(methods=["POST"])
@endpoint
def create(
	account_name,
	workspace_name,
	business_name=None,
	business_nature=None,
	owner_user=None,
	plan=None,
	referral_code=None,
	values=None,
	account=None,
):
	user = require_login()
	values = json_value(values, {})
	if business_nature:
		values["business_nature"] = business_nature
	if referral_code:
		values["referral_code"] = referral_code
	owner = owner_user if owner_user and is_operator(user) else user
	if account:
		account_doc = frappe.get_doc("VerityAI Account", account)
		if not is_operator(user) and account_doc.owner_user != owner:
			frappe.throw("You do not own this account.", frappe.PermissionError)
		account_name = account_doc.account_name
	return create_workspace(owner, account_name, workspace_name, business_name, plan, values)


@frappe.whitelist(methods=["POST"])
@endpoint
def update_step(workspace, step_code, status="Done"):
	check_workspace_access(workspace)
	return {"setup_progress": set_step(workspace, step_code, status)}


@frappe.whitelist(methods=["POST"])
@endpoint
def finish(workspace):
	user = require_login()
	check_workspace_access(workspace)
	return complete_setup(workspace, user=user)
