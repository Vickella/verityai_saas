import frappe
from frappe.rate_limiter import rate_limit

from verityai_saas.api._response import endpoint, json_value
from verityai_saas.growth import audits
from verityai_saas.services.permissions import require_platform_admin, require_workspace_permission


@frappe.whitelist(allow_guest=True, methods=["POST"])
@endpoint
@rate_limit(key="verityai_public_website_audit", limit=5, seconds=60 * 60, methods=["POST"], ip_based=True)
def start(url):
	return audits.request_public_audit(url)


@frappe.whitelist(allow_guest=True, methods=["POST"])
@endpoint
@rate_limit(key="verityai_public_website_audit_status", limit=60, seconds=60 * 60, methods=["POST"], ip_based=True)
def status(audit, token):
	return audits.public_status(audit, token)


@frappe.whitelist(allow_guest=True, methods=["POST"])
@endpoint
@rate_limit(key="verityai_public_website_audit_lead", limit=5, seconds=60 * 60, methods=["POST"], ip_based=True)
def capture_lead(audit, token, values=None):
	return audits.capture_public_lead(audit, token, json_value(values, {}))


@frappe.whitelist(methods=["POST"])
@endpoint
def start_for_workspace(workspace, url):
	require_workspace_permission(workspace, "manage_website")
	return audits.request_workspace_audit(workspace, url)


@frappe.whitelist()
@endpoint
def list_for_workspace(workspace):
	require_workspace_permission(workspace, "view_website")
	return audits.workspace_audits(workspace)


@frappe.whitelist()
@endpoint
def detail_for_workspace(workspace, audit):
	require_workspace_permission(workspace, "view_website")
	return audits.workspace_audit(workspace, audit)


@frappe.whitelist(methods=["POST"])
@endpoint
def start_operator(url):
	require_platform_admin()
	return audits.request_operator_audit(url)
