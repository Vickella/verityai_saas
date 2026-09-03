import frappe

from verityai_saas.api._response import endpoint, json_value
from verityai_saas.services import growth
from verityai_saas.services.admin_reauth import require_admin_reauthentication
from verityai_saas.services.permissions import require_platform_admin


def _authorise_change():
	require_platform_admin()
	require_admin_reauthentication()


@frappe.whitelist(methods=["POST"])
@endpoint
def configure_feature_flags(values):
	_authorise_change()
	return growth.configure_feature_flags(json_value(values, {}))


@frappe.whitelist(methods=["POST"])
@endpoint
def save_channel(values, channel=None):
	_authorise_change()
	return growth.save_channel(json_value(values, {}), channel=channel)


@frappe.whitelist(methods=["POST"])
@endpoint
def save_campaign(values, campaign=None):
	_authorise_change()
	return growth.save_campaign(json_value(values, {}), campaign=campaign)


@frappe.whitelist(methods=["POST"])
@endpoint
def record_consent(values):
	_authorise_change()
	values = json_value(values, {})
	doc = growth.record_consent(
		values.get("identifier"), values.get("subject_type"), values.get("purpose"),
		status=values.get("status") or "Granted", channel=values.get("channel"), source=values.get("source"),
		expires_on=values.get("expires_on"), evidence=values.get("evidence"),
	)
	return {"record": doc.name}


@frappe.whitelist(methods=["POST"])
@endpoint
def suppress_identity(values):
	_authorise_change()
	values = json_value(values, {})
	doc = growth.suppress(
		values.get("identifier"), values.get("reason"), channel=values.get("channel"),
		expires_on=values.get("expires_on"), source="Operator console",
	)
	return {"record": doc.name}


@frappe.whitelist(methods=["POST"])
@endpoint
def lift_suppression(record):
	_authorise_change()
	doc = growth.lift_suppression(record)
	return {"record": doc.name, "status": doc.status}
