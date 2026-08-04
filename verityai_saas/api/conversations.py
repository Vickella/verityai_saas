import csv
import io

import frappe
from frappe.utils import cint

from verityai_saas.api._response import endpoint
from verityai_saas.services import crm, engine
from verityai_saas.services.permissions import require_workspace_permission


def _filters(platform=None, status=None, search=None, limit=50, start=0):
	return {"platform": platform, "status": status, "search": search, "limit": min(max(cint(limit or 50), 1), 200), "start": max(cint(start or 0), 0)}


@frappe.whitelist()
@endpoint
def list_conversations(workspace, platform=None, status=None, search=None, limit=50, start=0):
	require_workspace_permission(workspace, "view_conversations")
	filters = _filters(platform, status, search, limit, start)
	rows = crm.decorate_conversations(workspace, engine.get_workspace_conversations(workspace, filters))
	return {"rows": rows, "start": filters["start"], "limit": filters["limit"], "has_more": len(rows) == filters["limit"]}


@frappe.whitelist()
@endpoint
def detail(workspace, conversation):
	require_workspace_permission(workspace, "view_conversations")
	data = engine.get_conversation(workspace, conversation)
	data["handoff"] = crm.handoff_data(workspace, conversation)
	return data


@frappe.whitelist(methods=["POST"])
@endpoint
def update_handoff(workspace, conversation, status, assigned_to=None, note=None):
	require_workspace_permission(workspace, "manage_conversations")
	return crm.update_handoff(workspace, conversation, status, assigned_to, note)


@frappe.whitelist()
@endpoint
def assignees(workspace):
	require_workspace_permission(workspace, "view_conversations")
	return crm.workspace_assignees(workspace)


def _csv_safe(value):
	value = str(value or "")
	return chr(9) + value if value[:1] in {"=", "+", "-", "@"} else value


@frappe.whitelist()
def export_csv(workspace, platform=None, status=None, search=None):
	require_workspace_permission(workspace, "view_conversations")
	rows, start = [], 0
	while len(rows) < 10000:
		page = engine.get_workspace_conversations(workspace, _filters(platform, status, search, 200, start))
		rows.extend(page)
		if len(page) < 200:
			break
		start += 200
	rows = crm.decorate_conversations(workspace, rows)
	fields = ["name", "session_id", "platform", "user_identifier", "status", "estimated_deal_value", "modified"]
	output = io.StringIO(newline="")
	writer = csv.writer(output)
	writer.writerow(fields + ["handoff_status", "assigned_to"])
	for row in rows:
		handoff = row.get("handoff") or {}
		writer.writerow([_csv_safe(row.get(field)) for field in fields] + [_csv_safe(handoff.get("status")), _csv_safe(handoff.get("assigned_to"))])
	frappe.local.response.filename = "verityai-conversations.csv"
	frappe.local.response.filecontent = output.getvalue().encode("utf-8-sig")
	frappe.local.response.type = "download"
