import frappe
from frappe.utils import cint

from verityai_saas.api._response import endpoint, json_value
from verityai_saas.services import analytics
from verityai_saas.services.permissions import check_workspace_access, require_operator


@frappe.whitelist()
@endpoint
def get(workspace, from_date=None, to_date=None):
	check_workspace_access(workspace)
	return analytics.workspace_analytics(workspace, from_date, to_date)


@frappe.whitelist()
def export_workspace(workspace, from_date=None, to_date=None):
	check_workspace_access(workspace)
	frappe.local.response.filename = f"{workspace}-analytics.zip"
	frappe.local.response.filecontent = analytics.workspace_export(workspace, from_date, to_date)
	frappe.local.response.type = "download"


def _schedule_values(values, doc=None):
	values = json_value(values, {})
	doc = doc or frappe.get_doc({"doctype": "VerityAI Report Schedule"})
	if "report_name" in values:
		doc.report_name = (values.get("report_name") or "").strip()
	if not doc.report_name:
		frappe.throw("Report name is required.", frappe.ValidationError)
	if "report_type" in values:
		doc.report_type = values.get("report_type")
	if doc.report_type not in {"Operator Summary", "Workspace Analytics"}:
		frappe.throw("Unsupported report type.", frappe.ValidationError)
	if "workspace" in values:
		doc.workspace = values.get("workspace") or None
	if doc.report_type == "Workspace Analytics" and not doc.workspace:
		frappe.throw("Workspace Analytics schedules require a workspace.", frappe.ValidationError)
	if "recipients" in values:
		recipients = analytics.normalize_recipients(values.get("recipients"))
		if not recipients:
			frappe.throw("At least one valid report recipient is required.", frappe.ValidationError)
		doc.recipients = ", ".join(recipients)
	if "frequency" in values:
		if values.get("frequency") not in {"Daily", "Weekly", "Monthly"}:
			frappe.throw("Unsupported report frequency.", frappe.ValidationError)
		doc.frequency = values.get("frequency")
	if "active" in values:
		doc.active = 1 if cint(values.get("active")) else 0
	if not doc.next_send_on or "frequency" in values:
		doc.next_send_on = analytics.next_send(doc.frequency or "Weekly")
	return doc


@frappe.whitelist()
@endpoint
def schedules():
	require_operator()
	return frappe.get_all("VerityAI Report Schedule", fields=["name", "report_name", "report_type", "workspace", "recipients", "frequency", "active", "last_sent_on", "next_send_on", "last_status", "last_error"], order_by="creation desc", limit=200)


@frappe.whitelist(methods=["POST"])
@endpoint
def create_schedule(values):
	require_operator()
	doc = _schedule_values(values)
	doc.insert(ignore_permissions=True)
	return {"schedule": doc.name}


@frappe.whitelist(methods=["POST"])
@endpoint
def update_schedule(schedule, values):
	require_operator()
	if not frappe.db.exists("VerityAI Report Schedule", schedule):
		frappe.throw("Report schedule was not found.", frappe.DoesNotExistError)
	doc = _schedule_values(values, frappe.get_doc("VerityAI Report Schedule", schedule))
	doc.save(ignore_permissions=True)
	return {"schedule": doc.name}


@frappe.whitelist()
def operator_export():
	require_operator()
	frappe.local.response.filename = "verityai-operator-summary.csv"
	frappe.local.response.filecontent = analytics.operator_summary_csv()
	frappe.local.response.type = "download"
