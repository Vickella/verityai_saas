import frappe

from verityai_saas.api._response import endpoint, json_value
from verityai_saas.services import engine
from verityai_saas.services.onboarding import set_step
from verityai_saas.services.permissions import check_workspace_access, require_workspace_permission


@frappe.whitelist()
@endpoint
def list_sources(workspace):
	check_workspace_access(workspace)
	return engine.list_knowledge_sources(workspace)


@frappe.whitelist()
@endpoint
def create(workspace, title, content=None, file=None):
	require_workspace_permission(workspace, "manage_knowledge")
	name = engine.create_knowledge_source(workspace, title, content, file)
	set_step(workspace, "knowledge")
	return {"source": name}


@frappe.whitelist()
@endpoint
def update(workspace, source, values):
	require_workspace_permission(workspace, "manage_knowledge")
	return {"source": engine.update_knowledge_source(workspace, source, json_value(values, {}))}

