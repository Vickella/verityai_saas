import frappe

from verityai_saas.api._response import endpoint, json_value
from verityai_saas.services import campaigns
from verityai_saas.services.permissions import require_workspace_permission


@frappe.whitelist()
@endpoint
def list_campaigns(workspace, status=None, channel=None, search=None):
	require_workspace_permission(workspace, "view_campaigns")
	return campaigns.list_campaigns(workspace, status=status, channel=channel, search=search)


@frappe.whitelist()
@endpoint
def detail(workspace, campaign):
	require_workspace_permission(workspace, "view_campaigns")
	return campaigns.campaign_detail(workspace, campaign)


@frappe.whitelist(methods=["POST"])
@endpoint
def create(workspace, values):
	require_workspace_permission(workspace, "manage_campaigns")
	return campaigns.create_campaign(workspace, json_value(values, {}))


@frappe.whitelist(methods=["POST"])
@endpoint
def update(workspace, campaign, values):
	require_workspace_permission(workspace, "manage_campaigns")
	return campaigns.update_campaign(workspace, campaign, json_value(values, {}))


@frappe.whitelist(methods=["POST"])
@endpoint
def set_status(workspace, campaign, status):
	require_workspace_permission(workspace, "manage_campaigns")
	return campaigns.set_status(workspace, campaign, status)


@frappe.whitelist(methods=["POST"])
@endpoint
def delete(workspace, campaign):
	require_workspace_permission(workspace, "manage_campaigns")
	return campaigns.delete_campaign(workspace, campaign)
