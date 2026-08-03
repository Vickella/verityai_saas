import frappe

from verityai_saas.api._response import endpoint
from verityai_saas.services.health import workspace_health


@frappe.whitelist()
@endpoint
def get(workspace, status=None, severity=None, limit=100):
	return workspace_health(workspace, status=status, severity=severity, limit=limit)
