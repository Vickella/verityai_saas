import hashlib
from html import escape

import frappe
from frappe.utils import add_days, flt, getdate, today


DOCUMENT_PREFIXES = {
	"Invoice": "INV",
	"Receipt": "RCT",
	"Credit Note": "CRN",
	"Refund Confirmation": "RFD",
}
SAFE_FIELDS = (
	"name", "document_number", "document_type", "status", "issue_date", "due_date", "paid_on",
	"currency", "subtotal", "tax_amount", "total", "provider_reference", "billing_event", "creation",
)


def _money(value):
	return f"{flt(value):,.2f}"


def _render(document_type, number, workspace, account, event, issue_date, due_date=None):
	reference = event.gateway_reference or event.provider_reference or event.name
	status_line = f"<p><strong>Due:</strong> {escape(str(due_date))}</p>" if due_date else ""
	return f"""<!doctype html><html><head><meta charset="utf-8"><style>
	body{{font-family:Arial,sans-serif;color:#172033;margin:40px}}h1{{color:#123f78}}
	table{{width:100%;border-collapse:collapse;margin-top:24px}}td,th{{padding:10px;border-bottom:1px solid #d9e1ec;text-align:left}}
	.total{{font-size:1.2em;font-weight:bold}}.muted{{color:#667085}}</style></head><body>
	<h1>VerityAI {escape(document_type)}</h1><p class="muted">VerityCore Consultancy (Pvt) Ltd</p>
	<p><strong>Document:</strong> {escape(number)}</p><p><strong>Issued:</strong> {escape(str(issue_date))}</p>{status_line}
	<h2>Bill to</h2><p>{escape(account.account_name)}<br>{escape(account.billing_email or '')}</p>
	<h2>Workspace</h2><p>{escape(workspace.business_name or workspace.workspace_name)}</p>
	<table><thead><tr><th>Description</th><th>Reference</th><th>Amount</th></tr></thead><tbody>
	<tr><td>{escape(event.event_type)} via {escape(event.provider or 'Manual')}</td><td>{escape(str(reference))}</td><td>{escape(event.currency or workspace.currency or 'USD')} {_money(event.amount)}</td></tr>
	<tr class="total"><td colspan="2">Total</td><td>{escape(event.currency or workspace.currency or 'USD')} {_money(event.amount)}</td></tr>
	</tbody></table><p class="muted">Generated securely by VerityAI. Verify this document in your authenticated billing portal.</p></body></html>"""


def ensure_document(billing_event, document_type, status=None, due_date=None):
	if document_type not in DOCUMENT_PREFIXES:
		frappe.throw("Unsupported billing document type.", frappe.ValidationError)
	existing = frappe.db.get_value("VerityAI Billing Document", {
		"billing_event": billing_event, "document_type": document_type,
	}, "name")
	if existing:
		return existing
	event = frappe.get_doc("VerityAI Billing Event", billing_event)
	workspace = frappe.get_doc("VerityAI Workspace", event.workspace)
	account = frappe.get_doc("VerityAI Account", event.account)
	issue_date = getdate(today())
	due_date = getdate(due_date) if due_date else add_days(issue_date, 7) if document_type == "Invoice" else None
	number = f"{DOCUMENT_PREFIXES[document_type]}-{issue_date.year}-{event.name.replace('-', '')[-12:]}"
	html = _render(document_type, number, workspace, account, event, issue_date, due_date)
	doc = frappe.get_doc({
		"doctype": "VerityAI Billing Document", "workspace": workspace.name, "account": account.name,
		"subscription": event.subscription, "billing_event": event.name, "document_type": document_type,
		"document_number": number, "status": status or ("Paid" if document_type in {"Receipt", "Refund Confirmation"} else "Issued"),
		"issue_date": issue_date, "due_date": due_date, "paid_on": event.paid_on,
		"currency": event.currency or workspace.currency or "USD", "subtotal": event.amount,
		"tax_amount": 0, "total": event.amount, "provider_reference": event.gateway_reference or event.provider_reference,
		"rendered_html": html, "checksum": hashlib.sha256(html.encode("utf-8")).hexdigest(),
	}).insert(ignore_permissions=True)
	return doc.name


def ensure_invoice_for_payment(payment_event):
	return ensure_document(payment_event, "Invoice", status="Issued")


def ensure_receipt_for_payment(payment_event):
	event = frappe.get_doc("VerityAI Billing Event", payment_event)
	if event.event_type != "Payment" or event.status != "Completed":
		return None
	invoice = frappe.db.get_value("VerityAI Billing Document", {"billing_event": event.name, "document_type": "Invoice"}, "name")
	if invoice:
		frappe.db.set_value("VerityAI Billing Document", invoice, {"status": "Paid", "paid_on": event.paid_on})
	return ensure_document(event.name, "Receipt", status="Paid")


def ensure_refund_confirmation(refund_event):
	event = frappe.get_doc("VerityAI Billing Event", refund_event)
	if event.event_type != "Refund" or event.status != "Completed":
		return None
	return ensure_document(event.name, "Refund Confirmation", status="Paid")


def list_documents(workspace_name, limit=100):
	return frappe.get_all(
		"VerityAI Billing Document", filters={"workspace": workspace_name}, fields=list(SAFE_FIELDS),
		order_by="issue_date desc, creation desc", limit=min(max(int(limit or 100), 1), 200),
	)
