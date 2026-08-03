import frappe

from verityai_saas.api._response import endpoint
from verityai_saas.services import engine
from verityai_saas.services.permissions import require_workspace_permission


@frappe.whitelist()
@endpoint
def list_leads(workspace, status=None, source_channel=None, search=None, limit=50):
	require_workspace_permission(workspace, "view_leads")
	return engine.get_workspace_leads(workspace, {"status": status, "source_channel": source_channel, "search": search, "limit": limit})


@frappe.whitelist()
@endpoint
def detail(workspace, lead):
	require_workspace_permission(workspace, "view_leads")
	tenant = engine.get_workspace_engine_tenant(workspace)
	if not frappe.db.exists("AI Lead", {"name": lead, "tenant": tenant}):
		frappe.throw("Lead was not found.", frappe.DoesNotExistError)
	return frappe.db.get_value("AI Lead", lead, ["name", "lead_name", "email", "phone", "business_type", "location", "enquiry_type", "requirements", "dynamic_details", "source_channel", "status", "chat_session", "creation", "modified"], as_dict=True)


@frappe.whitelist()
@endpoint
def update_status(workspace, lead, status):
	require_workspace_permission(workspace, "manage_leads")
	tenant = engine.get_workspace_engine_tenant(workspace)
	if status not in {"New", "Contacted", "Qualified", "Won", "Lost"}:
		frappe.throw("Unsupported lead status.", frappe.ValidationError)
	if not frappe.db.exists("AI Lead", {"name": lead, "tenant": tenant}):
		frappe.throw("Lead was not found.", frappe.DoesNotExistError)
	frappe.db.set_value("AI Lead", lead, "status", status)
	return {"lead": lead, "status": status}

