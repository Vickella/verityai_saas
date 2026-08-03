import frappe

from verityai_saas.api._response import endpoint
from verityai_saas.services import engine
from verityai_saas.services.permissions import require_workspace_permission


@frappe.whitelist()
@endpoint
def list_conversations(workspace, platform=None, status=None, limit=50):
	require_workspace_permission(workspace, "view_conversations")
	return engine.get_workspace_conversations(workspace, {"platform": platform, "status": status, "limit": limit})


@frappe.whitelist()
@endpoint
def detail(workspace, conversation):
	require_workspace_permission(workspace, "view_conversations")
	return engine.get_conversation(workspace, conversation)

