import frappe

from verityai_saas.api._response import endpoint, json_value
from verityai_saas.services.permissions import require_workspace_permission
from verityai_saas.websites import projects


@frappe.whitelist()
@endpoint
def list_projects(workspace):
	require_workspace_permission(workspace, "view_website")
	return projects.list_projects(workspace)


@frappe.whitelist()
@endpoint
def detail(workspace, project):
	require_workspace_permission(workspace, "view_website")
	return projects.get_project(workspace, project)


@frappe.whitelist(methods=["POST"])
@endpoint
def create(workspace, values):
	require_workspace_permission(workspace, "manage_website")
	return projects.create_project(workspace, json_value(values, {}))


@frappe.whitelist(methods=["POST"])
@endpoint
def update(workspace, project, values):
	require_workspace_permission(workspace, "manage_website")
	return projects.update_project(workspace, project, json_value(values, {}))


@frappe.whitelist(methods=["POST"])
@endpoint
def add_version(workspace, project, definition, source="Manual"):
	require_workspace_permission(workspace, "manage_website")
	return projects.add_definition_version(workspace, project, json_value(definition, {}), source=source)


@frappe.whitelist(methods=["POST"])
@endpoint
def select_version(workspace, project, version):
	require_workspace_permission(workspace, "manage_website")
	return projects.set_current_version(workspace, project, version)


@frappe.whitelist(methods=["POST"])
@endpoint
def change_status(workspace, project, status):
	require_workspace_permission(workspace, "manage_website")
	return projects.set_status(workspace, project, status)
