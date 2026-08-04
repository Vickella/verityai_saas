import frappe

from verityai_saas.api._response import endpoint
from verityai_saas.services import engine
from verityai_saas.services.entitlements import require_workspace_feature
from verityai_saas.services.permissions import require_workspace_permission


@frappe.whitelist()
@endpoint
def list_requests(workspace, status=None, limit=100):
	require_workspace_permission(workspace, "approve_quotes")
	return engine.get_workspace_quote_requests(workspace, status=status, limit=limit)


@frappe.whitelist(methods=["POST"])
@endpoint
def approve(workspace, quotation_request, notes=None):
	require_workspace_permission(workspace, "approve_quotes")
	return engine.approve_workspace_quote(workspace, quotation_request, notes=notes)
