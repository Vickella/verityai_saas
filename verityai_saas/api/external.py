import frappe
from frappe.utils import cint

from verityai_saas.api._response import endpoint
from verityai_saas.services import analytics, engine, integrations


@frappe.whitelist(allow_guest=True)
@endpoint
def leads(start=0, limit=50, status=None, search=None):
	context = integrations.authenticate_api("leads:read")
	return engine.get_workspace_leads(
		context.workspace.name,
		{"start": max(cint(start), 0), "limit": min(max(cint(limit), 1), 100), "status": status, "search": search},
	)


@frappe.whitelist(allow_guest=True)
@endpoint
def workspace_analytics(from_date=None, to_date=None):
	context = integrations.authenticate_api("analytics:read")
	return analytics.workspace_analytics(context.workspace.name, from_date, to_date)