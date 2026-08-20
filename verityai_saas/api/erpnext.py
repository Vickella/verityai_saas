import frappe

from verityai_saas.api._response import endpoint, json_value
from verityai_saas.services import erpnext
from verityai_saas.services.permissions import require_workspace_permission


@frappe.whitelist()
@endpoint
def get(workspace):
	require_workspace_permission(workspace, "view_catalog")
	return erpnext.status(workspace)


@frappe.whitelist(methods=["POST"])
@endpoint
def update(workspace, values):
	require_workspace_permission(workspace, "manage_catalog")
	return erpnext.configure(workspace, json_value(values, {}))


@frappe.whitelist(methods=["POST"])
@endpoint
def test(workspace):
	require_workspace_permission(workspace, "manage_catalog")
	return erpnext.test_connection(workspace)


@frappe.whitelist(methods=["POST"])
@endpoint
def sync_products(workspace):
	require_workspace_permission(workspace, "manage_catalog")
	return erpnext.sync_products(workspace)


@frappe.whitelist(methods=["POST"])
@endpoint
def sync_quotation(workspace, quotation):
	require_workspace_permission(workspace, "manage_quotes")
	return erpnext.sync_quotation(workspace, quotation)
