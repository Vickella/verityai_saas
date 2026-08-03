import frappe

from verityai_saas.api._response import endpoint, json_value
from verityai_saas.services import engine
from verityai_saas.services.onboarding import set_step
from verityai_saas.services.permissions import check_workspace_access, require_workspace_permission


@frappe.whitelist()
@endpoint
def get(workspace):
	check_workspace_access(workspace)
	data = engine.safe_settings(workspace)
	data["embed_code"] = engine.generate_embed_code(workspace)
	return data


@frappe.whitelist()
@endpoint
def update(workspace, values):
	require_workspace_permission(workspace, "manage_widget")
	data = engine.update_widget_settings(workspace, json_value(values, {}))
	set_step(workspace, "widget")
	return data


@frappe.whitelist()
@endpoint
def set_domains(workspace, domains):
	require_workspace_permission(workspace, "manage_widget")
	data = engine.replace_allowed_domains(workspace, json_value(domains, []))
	if data:
		set_step(workspace, "domain")
	return {"allowed_domains": data, "embed_code": engine.generate_embed_code(workspace)}


@frappe.whitelist()
@endpoint
def embed_code(workspace):
	check_workspace_access(workspace)
	return {"embed_code": engine.generate_embed_code(workspace)}

