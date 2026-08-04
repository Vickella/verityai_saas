import json

import frappe
from frappe.utils import now_datetime

from verityai_saas.services import engine


LEAD_STATUSES = {"New", "Contacted", "Qualified", "Won", "Lost"}
HANDOFF_STATUSES = {"Open", "Assigned", "Resolved"}


def _workspace_tenant(workspace_name):
	return engine.get_workspace_engine_tenant(workspace_name)


def require_lead(workspace_name, lead_name):
	tenant = _workspace_tenant(workspace_name)
	if not frappe.db.exists("AI Lead", {"name": lead_name, "tenant": tenant}):
		frappe.throw("Lead was not found.", frappe.DoesNotExistError)
	return frappe.get_doc("AI Lead", lead_name)


def require_conversation(workspace_name, conversation_name):
	tenant = _workspace_tenant(workspace_name)
	if not frappe.db.exists("AI Chat Session", {"name": conversation_name, "tenant": tenant}):
		frappe.throw("Conversation was not found.", frappe.DoesNotExistError)
	return frappe.get_doc("AI Chat Session", conversation_name)


def workspace_assignees(workspace_name):
	workspace = frappe.get_doc("VerityAI Workspace", workspace_name)
	users = {workspace.owner_user}
	users.update(frappe.get_all("VerityAI Workspace Member", filters={"workspace": workspace_name, "status": "Active"}, pluck="user"))
	return sorted(user for user in users if user and frappe.db.exists("User", {"name": user, "enabled": 1}))


def validate_assignee(workspace_name, user):
	if user and user not in workspace_assignees(workspace_name):
		frappe.throw("Assignee must be an active workspace member.", frappe.ValidationError)
	return user or None


def record_lead_activity(workspace_name, lead_name, activity_type, note=None, assigned_to=None, old_status=None, new_status=None):
	require_lead(workspace_name, lead_name)
	return frappe.get_doc({
		"doctype": "VerityAI Lead Activity", "workspace": workspace_name, "lead": lead_name,
		"activity_type": activity_type, "note": (note or "").strip()[:2000] or None,
		"assigned_to": assigned_to, "old_status": old_status, "new_status": new_status,
		"performed_by": frappe.session.user,
	}).insert(ignore_permissions=True).name


def assign_lead(workspace_name, lead_name, assigned_to, note=None):
	assigned_to = validate_assignee(workspace_name, assigned_to)
	activity = record_lead_activity(workspace_name, lead_name, "Assignment", note, assigned_to=assigned_to)
	return {"lead": lead_name, "assigned_to": assigned_to, "activity": activity}


def add_lead_note(workspace_name, lead_name, note):
	if not (note or "").strip():
		frappe.throw("Lead note is required.", frappe.ValidationError)
	activity = record_lead_activity(workspace_name, lead_name, "Note", note)
	return {"lead": lead_name, "activity": activity}


def update_lead_status(workspace_name, lead_name, status, note=None):
	if status not in LEAD_STATUSES:
		frappe.throw("Unsupported lead status.", frappe.ValidationError)
	lead = require_lead(workspace_name, lead_name)
	old_status = lead.status
	if old_status != status:
		lead.status = status
		lead.save(ignore_permissions=True)
	activity = record_lead_activity(workspace_name, lead_name, "Status Change", note, old_status=old_status, new_status=status)
	return {"lead": lead_name, "status": status, "activity": activity}


def lead_activities(workspace_name, lead_name, limit=100):
	require_lead(workspace_name, lead_name)
	return frappe.get_all("VerityAI Lead Activity", filters={"workspace": workspace_name, "lead": lead_name}, fields=["name", "activity_type", "note", "assigned_to", "old_status", "new_status", "performed_by", "creation"], order_by="creation desc", limit=min(max(int(limit or 100), 1), 200))


def decorate_leads(workspace_name, rows):
	lead_names = [row.name for row in rows]
	if not lead_names:
		return rows
	assignments = frappe.get_all("VerityAI Lead Activity", filters={"workspace": workspace_name, "lead": ["in", lead_names], "activity_type": "Assignment"}, fields=["lead", "assigned_to", "creation"], order_by="creation desc")
	latest = {}
	for row in assignments:
		latest.setdefault(row.lead, row.assigned_to)
	note_counts = dict(frappe.get_all("VerityAI Lead Activity", filters={"workspace": workspace_name, "lead": ["in", lead_names], "activity_type": "Note"}, fields=["lead", "count(name) as count"], group_by="lead", as_list=True))
	for row in rows:
		row["assigned_to"] = latest.get(row.name)
		row["note_count"] = note_counts.get(row.name, 0)
	return rows


def update_handoff(workspace_name, conversation_name, status, assigned_to=None, note=None):
	if status not in HANDOFF_STATUSES:
		frappe.throw("Unsupported handoff status.", frappe.ValidationError)
	conversation = require_conversation(workspace_name, conversation_name)
	assigned_to = validate_assignee(workspace_name, assigned_to)
	if status == "Assigned" and not assigned_to:
		frappe.throw("An assignee is required for an assigned handoff.", frappe.ValidationError)
	name = frappe.db.get_value("VerityAI Conversation Handoff", {"workspace": workspace_name, "conversation": conversation_name}, "name")
	handoff = frappe.get_doc("VerityAI Conversation Handoff", name) if name else frappe.get_doc({"doctype": "VerityAI Conversation Handoff", "workspace": workspace_name, "conversation": conversation_name, "opened_on": now_datetime(), "history_json": "[]"})
	try:
		history = json.loads(handoff.history_json or "[]")
	except (TypeError, ValueError):
		history = []
	history.append({"status": status, "assigned_to": assigned_to, "note": (note or "").strip()[:2000], "user": frappe.session.user, "timestamp": str(now_datetime())})
	handoff.status = status
	handoff.assigned_to = assigned_to
	handoff.history_json = frappe.as_json(history[-100:])
	if status == "Resolved":
		handoff.resolved_on = now_datetime()
		handoff.resolved_by = frappe.session.user
	else:
		handoff.resolved_on = None
		handoff.resolved_by = None
	if handoff.get("__islocal"):
		handoff.insert(ignore_permissions=True)
	else:
		handoff.save(ignore_permissions=True)
	conversation.status = "Closed" if status == "Resolved" else "Human Handoff"
	conversation.save(ignore_permissions=True)
	return handoff_data(workspace_name, conversation_name)


def handoff_data(workspace_name, conversation_name):
	require_conversation(workspace_name, conversation_name)
	name = frappe.db.get_value("VerityAI Conversation Handoff", {"workspace": workspace_name, "conversation": conversation_name}, "name")
	if not name:
		return None
	doc = frappe.get_doc("VerityAI Conversation Handoff", name)
	try:
		history = json.loads(doc.history_json or "[]")
	except (TypeError, ValueError):
		history = []
	return {"name": doc.name, "status": doc.status, "assigned_to": doc.assigned_to, "opened_on": doc.opened_on, "resolved_on": doc.resolved_on, "resolved_by": doc.resolved_by, "history": history}


def decorate_conversations(workspace_name, rows):
	names = [row.name for row in rows]
	if not names:
		return rows
	handoffs = frappe.get_all("VerityAI Conversation Handoff", filters={"workspace": workspace_name, "conversation": ["in", names]}, fields=["conversation", "status", "assigned_to", "opened_on", "resolved_on"])
	by_conversation = {row.conversation: row for row in handoffs}
	for row in rows:
		row["handoff"] = by_conversation.get(row.name)
	return rows


def funnel(workspace_name):
	tenant = _workspace_tenant(workspace_name)
	counts = {status: 0 for status in LEAD_STATUSES}
	for row in frappe.get_all("AI Lead", filters={"tenant": tenant}, fields=["status", "count(name) as total"], group_by="status"):
		counts[row.status] = row.total
	total = sum(counts.values())
	return {"counts": counts, "total": total, "qualified_rate": round((counts["Qualified"] + counts["Won"]) * 100 / total, 1) if total else 0, "win_rate": round(counts["Won"] * 100 / total, 1) if total else 0}
