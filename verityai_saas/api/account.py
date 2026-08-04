import frappe
from frappe.utils import cint, validate_email_address

from verityai_saas.api._response import endpoint, json_value
from verityai_saas.services.entitlements import workspace_context
from verityai_saas.services.permissions import check_workspace_access, is_operator, require_login


SAFE_FIELDS = ("account_name", "billing_email", "phone", "country", "currency", "customer_type")
EDITABLE_FIELDS = ("billing_email", "phone", "country", "currency", "customer_type")


def _account_for_workspace(workspace_name, require_owner=False):
	user = require_login()
	workspace = check_workspace_access(workspace_name, user)
	if require_owner and not is_operator(user) and workspace.owner_user != user:
		frappe.throw("Only the account owner can update this profile.", frappe.PermissionError)
	return workspace, frappe.get_doc("VerityAI Account", workspace.account)


@frappe.whitelist()
@endpoint
def get(workspace):
	workspace_doc, account = _account_for_workspace(workspace)
	context = workspace_context(workspace_name=workspace_doc.name)
	plan = context.plan if context else None
	workspace_count = frappe.db.count("VerityAI Workspace", {"account": account.name})
	workspace_limit = cint(plan.max_workspaces) if plan else 0
	return {
		"name": account.name,
		**{field: account.get(field) for field in SAFE_FIELDS},
		"workspace_count": workspace_count,
		"workspace_limit": workspace_limit,
		"can_add_workspace": not workspace_limit or workspace_count < workspace_limit,
		"plan": plan.name if plan else None,
	}


@frappe.whitelist(methods=["POST"])
@endpoint
def update(workspace, values):
	workspace_doc, account = _account_for_workspace(workspace, require_owner=True)
	values = json_value(values, {})
	for field in EDITABLE_FIELDS:
		if field not in values:
			continue
		value = (values.get(field) or "").strip()
		if field == "billing_email":
			validate_email_address(value, throw=True)
		elif field == "customer_type" and value not in {"SME", "Agency", "Enterprise"}:
			frappe.throw("Unsupported customer type.", frappe.ValidationError)
		setattr(account, field, value or None)
	account.save(ignore_permissions=True)
	return {field: account.get(field) for field in SAFE_FIELDS}
