import csv
import io
import zipfile
from collections import defaultdict
from datetime import timedelta

import frappe
from frappe.utils import add_days, add_months, getdate, now_datetime, today, validate_email_address

from verityai_saas.services import crm, engine


MAX_REPORT_DAYS = 366


def report_range(from_date=None, to_date=None):
	end = getdate(to_date or today())
	start = getdate(from_date or add_days(end, -29))
	if start > end:
		frappe.throw("Report start date cannot be after the end date.", frappe.ValidationError)
	if (end - start).days + 1 > MAX_REPORT_DAYS:
		frappe.throw(f"Report range cannot exceed {MAX_REPORT_DAYS} days.", frappe.ValidationError)
	return start, end


def _series(start, end, rows, value_fields):
	by_date = {str(row.date): row for row in rows}
	result = []
	current = start
	while current <= end:
		row = by_date.get(str(current), {})
		result.append({"date": str(current), **{field: float(row.get(field) or 0) for field in value_fields}})
		current += timedelta(days=1)
	return result


def workspace_analytics(workspace_name, from_date=None, to_date=None):
	start, end = report_range(from_date, to_date)
	tenant = engine.get_workspace_engine_tenant(workspace_name)
	end_time = f"{end} 23:59:59"
	usage_rows = frappe.db.sql("""select date(creation) as date, coalesce(sum(total_tokens),0) as tokens, coalesce(sum(estimated_cost),0) as cost, count(name) as requests from `tabAI Usage Log` where tenant=%s and creation between %s and %s group by date(creation) order by date(creation)""", (tenant, start, end_time), as_dict=True)
	lead_rows = frappe.db.sql("""select date(creation) as date, count(name) as leads from `tabAI Lead` where tenant=%s and creation between %s and %s group by date(creation) order by date(creation)""", (tenant, start, end_time), as_dict=True)
	conversation_rows = frappe.db.sql("""select date(creation) as date, count(name) as conversations from `tabAI Chat Session` where tenant=%s and creation between %s and %s group by date(creation) order by date(creation)""", (tenant, start, end_time), as_dict=True)
	channel_rows = frappe.get_all("AI Chat Session", filters={"tenant": tenant, "creation": ["between", [start, end_time]]}, fields=["platform", "count(name) as total"], group_by="platform")
	lead_status_rows = frappe.get_all("AI Lead", filters={"tenant": tenant, "creation": ["between", [start, end_time]]}, fields=["status", "count(name) as total"], group_by="status")
	billing_rows = frappe.db.sql("""select date(creation) as date, coalesce(sum(case when event_type='Payment' and status='Completed' then amount else 0 end),0) as revenue, coalesce(sum(case when event_type='Refund' and status='Completed' then amount else 0 end),0) as refunds from `tabVerityAI Billing Event` where workspace=%s and creation between %s and %s group by date(creation) order by date(creation)""", (workspace_name, start, end_time), as_dict=True)
	return {
		"from_date": str(start), "to_date": str(end),
		"usage": _series(start, end, usage_rows, ("tokens", "cost", "requests")),
		"leads": _series(start, end, lead_rows, ("leads",)),
		"conversations": _series(start, end, conversation_rows, ("conversations",)),
		"billing": _series(start, end, billing_rows, ("revenue", "refunds")),
		"channels": {row.platform or "Unknown": row.total for row in channel_rows},
		"lead_statuses": {row.status or "Unknown": row.total for row in lead_status_rows},
		"funnel": crm.funnel(workspace_name),
	}


def _csv_safe(value):
	value = str(value or "")
	return chr(9) + value if value[:1] in {"=", "+", "-", "@"} else value


def _csv_bytes(headers, rows):
	output = io.StringIO(newline="")
	writer = csv.writer(output)
	writer.writerow(headers)
	writer.writerows([_csv_safe(value) for value in row] for row in rows)
	return output.getvalue().encode("utf-8-sig")

def workspace_export(workspace_name, from_date=None, to_date=None):
	data = workspace_analytics(workspace_name, from_date, to_date)
	tenant = engine.get_workspace_engine_tenant(workspace_name)
	start, end = data["from_date"], data["to_date"]
	end_time = f"{end} 23:59:59"
	leads = frappe.get_all("AI Lead", filters={"tenant": tenant, "creation": ["between", [start, end_time]]}, fields=["name", "lead_name", "email", "phone", "source_channel", "status", "creation"], order_by="creation asc", limit_page_length=10000)
	conversations = frappe.get_all("AI Chat Session", filters={"tenant": tenant, "creation": ["between", [start, end_time]]}, fields=["name", "session_id", "platform", "user_identifier", "status", "estimated_deal_value", "creation", "modified"], order_by="creation asc", limit_page_length=10000)
	usage = frappe.get_all("AI Usage Log", filters={"tenant": tenant, "creation": ["between", [start, end_time]]}, fields=["name", "chat_session", "platform", "input_tokens", "output_tokens", "total_tokens", "estimated_cost", "status", "creation"], order_by="creation asc", limit_page_length=10000)
	billing = frappe.get_all("VerityAI Billing Event", filters={"workspace": workspace_name, "creation": ["between", [start, end_time]]}, fields=["name", "event_type", "amount", "currency", "status", "provider", "gateway_reference", "creation", "paid_on"], order_by="creation asc", limit_page_length=10000)
	files = {
		"usage-timeseries.csv": _csv_bytes(["date", "tokens", "cost", "requests"], [[row[key] for key in ("date", "tokens", "cost", "requests")] for row in data["usage"]]),
		"leads.csv": _csv_bytes(["name", "lead_name", "email", "phone", "source_channel", "status", "creation"], [[row.get(field) for field in ("name", "lead_name", "email", "phone", "source_channel", "status", "creation")] for row in leads]),
		"conversations.csv": _csv_bytes(["name", "session_id", "platform", "user_identifier", "status", "estimated_deal_value", "creation", "modified"], [[row.get(field) for field in ("name", "session_id", "platform", "user_identifier", "status", "estimated_deal_value", "creation", "modified")] for row in conversations]),
		"usage-events.csv": _csv_bytes(["name", "chat_session", "platform", "input_tokens", "output_tokens", "total_tokens", "estimated_cost", "status", "creation"], [[row.get(field) for field in ("name", "chat_session", "platform", "input_tokens", "output_tokens", "total_tokens", "estimated_cost", "status", "creation")] for row in usage]),
		"billing.csv": _csv_bytes(["name", "event_type", "amount", "currency", "status", "provider", "gateway_reference", "creation", "paid_on"], [[row.get(field) for field in ("name", "event_type", "amount", "currency", "status", "provider", "gateway_reference", "creation", "paid_on")] for row in billing]),
	}
	output = io.BytesIO()
	with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
		for filename, content in files.items():
			archive.writestr(filename, content)
	return output.getvalue()


def operator_summary_csv():
	rows = []
	for workspace in frappe.get_all("VerityAI Workspace", fields=["name", "business_name", "status", "engine_tenant"], order_by="name"):
		subscription = frappe.db.get_value("VerityAI Subscription", {"workspace": workspace.name}, ["plan", "status"], as_dict=True, order_by="creation desc") or {}
		wallet = frappe.db.get_value("VerityAI Usage Wallet", {"workspace": workspace.name}, ["tokens_used", "tokens_remaining", "status"], as_dict=True) or {}
		rows.append([workspace.name, workspace.business_name, workspace.status, subscription.get("plan"), subscription.get("status"), wallet.get("tokens_used"), wallet.get("tokens_remaining"), wallet.get("status"), frappe.db.count("AI Lead", {"tenant": workspace.engine_tenant}), frappe.db.count("AI Chat Session", {"tenant": workspace.engine_tenant})])
	return _csv_bytes(["workspace", "business_name", "workspace_status", "plan", "subscription_status", "tokens_used", "tokens_remaining", "wallet_status", "leads", "conversations"], rows)


def normalize_recipients(value):
	values = (value or "").replace(";", ",").replace("\n", ",").split(",")
	return sorted({email.strip().lower() for email in values if email.strip() and validate_email_address(email.strip())})


def next_send(frequency, base=None):
	base = base or now_datetime()
	if frequency == "Daily":
		return add_days(base, 1)
	if frequency == "Weekly":
		return add_days(base, 7)
	if frequency == "Monthly":
		return add_months(base, 1)
	frappe.throw("Unsupported report frequency.", frappe.ValidationError)


def send_due_reports():
	for row in frappe.get_all("VerityAI Report Schedule", filters={"active": 1, "next_send_on": ["<=", now_datetime()]}, fields=["name"]):
		doc = frappe.get_doc("VerityAI Report Schedule", row.name)
		try:
			recipients = normalize_recipients(doc.recipients)
			if not recipients:
				frappe.throw("A valid report recipient is required.", frappe.ValidationError)
			if doc.report_type == "Workspace Analytics":
				if not doc.workspace:
					frappe.throw("Workspace report schedule requires a workspace.", frappe.ValidationError)
				content = workspace_export(doc.workspace)
				filename, content_type = f"{doc.workspace}-analytics.zip", "application/zip"
			else:
				content = operator_summary_csv()
				filename, content_type = "verityai-operator-summary.csv", "text/csv"
			frappe.sendmail(recipients=recipients, subject=doc.report_name, message="Your scheduled VerityAI report is attached.", attachments=[{"fname": filename, "fcontent": content, "content_type": content_type}])
			doc.last_sent_on, doc.last_status, doc.last_error = now_datetime(), "Sent", None
			doc.next_send_on = next_send(doc.frequency)
		except Exception as exc:
			doc.last_status, doc.last_error = "Failed", str(exc)[:1000]
			doc.next_send_on = next_send(doc.frequency)
		doc.save(ignore_permissions=True)
	frappe.db.commit()
