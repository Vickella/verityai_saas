import frappe

from verityai_saas.api._response import endpoint, json_value
from verityai_saas.services import integrations, paynow
from verityai_saas.services.permissions import check_workspace_access, require_platform_admin


def _require_configuration_admin(workspace):
	require_platform_admin()
	return check_workspace_access(workspace)


@frappe.whitelist()
@endpoint
def get(workspace):
	_require_configuration_admin(workspace)
	status = integrations.integration_status(workspace)
	status["paynow"] = paynow.configuration_status()
	return status


@frappe.whitelist(methods=["POST"])
@endpoint
def update_paynow(workspace, values):
	_require_configuration_admin(workspace)
	return paynow.configure(json_value(values, {}))


@frappe.whitelist(methods=["POST"])
@endpoint
def update_provider(workspace, values):
	_require_configuration_admin(workspace)
	return integrations.configure_provider(workspace, json_value(values, {}))


@frappe.whitelist(methods=["POST"])
@endpoint
def update_erpnext(workspace, values):
	_require_configuration_admin(workspace)
	return integrations.configure_erpnext(workspace, json_value(values, {}))


@frappe.whitelist(methods=["POST"])
@endpoint
def update_smtp(workspace, values):
	_require_configuration_admin(workspace)
	return integrations.configure_smtp(workspace, json_value(values, {}))


@frappe.whitelist(methods=["POST"])
@endpoint
def create_credential(workspace, label, scopes):
	_require_configuration_admin(workspace)
	return integrations.create_api_credential(workspace, label, json_value(scopes, []))


@frappe.whitelist(methods=["POST"])
@endpoint
def revoke_credential(workspace, credential):
	_require_configuration_admin(workspace)
	return integrations.revoke_api_credential(workspace, credential)
