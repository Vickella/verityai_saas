import frappe

from verityai_saas.api._response import endpoint
from verityai_saas.services.permissions import require_operator
from verityai_saas.services.health import update_workspace_alert, workspace_health


@frappe.whitelist()
@endpoint
def get(workspace, status=None, severity=None, limit=100):
	return workspace_health(workspace, status=status, severity=severity, limit=limit)


@frappe.whitelist(methods=["POST"])
@endpoint
def update_alert(workspace, alert, status, note=None):
	require_operator()
	return update_workspace_alert(workspace, alert, status, note)