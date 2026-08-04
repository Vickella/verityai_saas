import csv
import io

import frappe
from frappe.utils import cint

from verityai_saas.api._response import endpoint
from verityai_saas.services import crm, engine
from verityai_saas.services.permissions import require_workspace_permission


def _filters(status=None, source_channel=None, search=None, limit=50, start=0):
	return {"status": status, "source_channel": source_channel, "search": search, "limit": min(max(cint(limit or 50), 1), 200), "start": max(cint(start or 0), 0)}


@frappe.whitelist()
@endpoint
def list_leads(workspace, status=None, source_channel=None, search=None, limit=50, start=0):
	require_workspace_permission(workspace, "view_leads")
	filters = _filters(status, source_channel, search, limit, start)
	rows = crm.decorate_leads(workspace, engine.get_workspace_leads(workspace, filters))
	return {"rows": rows, "start": filters["start"], "limit": filters["limit"], "has_more": len(rows) == filters["limit"], "funnel": crm.funnel(workspace)}


@frappe.whitelist()
@endpoint
def detail(workspace, lead):
	require_workspace_permission(workspace, "view_leads")
	doc = crm.require_lead(workspace, lead)
	fields = ["name", "lead_name", "email", "phone", "business_type", "location", "enquiry_type", "requirements", "dynamic_details", "source_channel", "status", "chat_session", "creation", "modified"]
	return {"lead": {field: doc.get(field) for field in fields}, "activities": crm.lead_activities(workspace, lead)}


@frappe.whitelist(methods=["POST"])
@endpoint
def update_status(workspace, lead, status, note=None):
	require_workspace_permission(workspace, "manage_leads")
	return crm.update_lead_status(workspace, lead, status, note)


@frappe.whitelist(methods=["POST"])
@endpoint
def assign(workspace, lead, assigned_to=None, note=None):
	require_workspace_permission(workspace, "manage_leads")
	return crm.assign_lead(workspace, lead, assigned_to, note)


@frappe.whitelist(methods=["POST"])
@endpoint
def add_note(workspace, lead, note):
	require_workspace_permission(workspace, "manage_leads")
	return crm.add_lead_note(workspace, lead, note)


@frappe.whitelist()
@endpoint
def assignees(workspace):
	require_workspace_permission(workspace, "view_leads")
	return crm.workspace_assignees(workspace)


def _csv_safe(value):
	value = str(value or "")
	return chr(9) + value if value[:1] in {"=", "+", "-", "@"} else value


@frappe.whitelist()
def export_csv(workspace, status=None, source_channel=None, search=None):
	require_workspace_permission(workspace, "view_leads")
	rows, start = [], 0
	while len(rows) < 10000:
		page = engine.get_workspace_leads(workspace, _filters(status, source_channel, search, 200, start))
		rows.extend(page)
		if len(page) < 200:
			break
		start += 200
	rows = crm.decorate_leads(workspace, rows)
	fields = ["name", "lead_name", "email", "phone", "source_channel", "status", "assigned_to", "creation", "modified"]
	output = io.StringIO(newline="")
	writer = csv.writer(output)
	writer.writerow(fields)
	for row in rows:
		writer.writerow([_csv_safe(row.get(field)) for field in fields])
	frappe.local.response.filename = "verityai-leads.csv"
	frappe.local.response.filecontent = output.getvalue().encode("utf-8-sig")
	frappe.local.response.type = "download"
