import frappe

from verityai_saas.api._response import endpoint, json_value
from verityai_saas.services import engine
from verityai_saas.services.onboarding import set_step
from verityai_saas.services.permissions import check_workspace_access, require_workspace_permission


@frappe.whitelist()
@endpoint
def get(workspace):
	check_workspace_access(workspace)
	return engine.safe_settings(workspace)


@frappe.whitelist()
@endpoint
def update(workspace, values):
	require_workspace_permission(workspace, "manage_assistant")
	data = engine.update_assistant_identity(workspace, json_value(values, {}))
	set_step(workspace, "assistant")
	if data.get("business_nature"):
		set_step(workspace, "business_nature")
	return data

