import frappe

from verityai_saas.api._response import endpoint, json_value
from verityai_saas.services import whatsapp
from verityai_saas.services.onboarding import set_step
from verityai_saas.services.permissions import check_workspace_access, require_workspace_permission


@frappe.whitelist()
@endpoint
def get(workspace):
	check_workspace_access(workspace)
	return whatsapp.safe_setup(workspace)


@frappe.whitelist()
@endpoint
def update(workspace, values):
	require_workspace_permission(workspace, "manage_whatsapp")
	data = whatsapp.configure(workspace, json_value(values, {}))
	set_step(workspace, "whatsapp")
	return data

