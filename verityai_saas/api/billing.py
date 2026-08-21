import csv
import io

import frappe

from verityai_saas.api._response import endpoint
from verityai_saas.services import billing, billing_documents, paynow
from verityai_saas.services.commercial import ensure_account_referral_code
from verityai_saas.services.admin_reauth import require_admin_reauthentication
from verityai_saas.services.permissions import check_workspace_access


@frappe.whitelist()
@endpoint
def get(workspace):
	workspace_doc = check_workspace_access(workspace)
	referral_code = ensure_account_referral_code(workspace_doc.account)
	return {
		"subscription": frappe.get_all("VerityAI Subscription", filters={"workspace": workspace}, fields=["name", "plan", "status", "billing_cycle", "trial_end", "current_period_end", "next_billing_date", "amount", "currency"], order_by="creation desc", limit=1),
		"wallet": frappe.db.get_value("VerityAI Usage Wallet", {"workspace": workspace}, ["opening_token_allowance", "top_up_tokens", "promotional_credits", "promotional_credits_expire_on", "tokens_used", "tokens_remaining", "status", "estimated_ai_cost"], as_dict=True),
		"events": frappe.get_all("VerityAI Billing Event", filters={"workspace": workspace}, fields=["name", "event_type", "transaction_kind", "amount", "gross_amount", "discount_amount", "purchased_credits", "currency", "status", "provider", "gateway_status", "gateway_reference", "creation", "paid_on"], order_by="creation desc", limit=50),
		"plans": frappe.get_all("VerityAI Plan", filters={"active": 1}, fields=["name", "plan_name", "plan_code", "monthly_price", "annual_price", "currency", "monthly_token_limit", "max_team_members", "monthly_web_conversations", "monthly_whatsapp_messages", "max_knowledge_sources", "max_allowed_domains", "can_remove_branding", "can_use_whatsapp_ai", "can_use_custom_smtp", "can_use_erpnext_integration", "can_use_api_access", "support_level"], order_by="monthly_price asc"),
		"credit_packs": frappe.get_all("VerityAI Credit Pack", filters={"active": 1}, fields=["name", "pack_name", "pack_code", "credits", "price", "currency"], order_by="sort_order asc"),
		"referral": {"code": referral_code, "reward_credits": 50000, "referred_discount_percent": 25},
		"documents": billing_documents.list_documents(workspace),
		"paynow_configured": paynow.is_configured(),
	}


@frappe.whitelist(methods=["POST"])
@endpoint
def manual_event(workspace, event_type, amount=0, status="Pending", reference=None):
	require_admin_reauthentication()
	return {"event": billing.create_billing_event(workspace, event_type, amount, status, provider_reference=reference)}


@frappe.whitelist(methods=["POST"])
@endpoint
def assign_plan(workspace, plan, status="Active", billing_cycle="Monthly"):
	operator = require_admin_reauthentication()
	subscription = billing.assign_plan(workspace, plan, status, billing_cycle)
	event = billing.create_billing_event(
		workspace,
		"Subscription Activation",
		0,
		"Completed",
		provider_reference=f"Plan {plan} set to {status} by {operator}",
	)
	return {"subscription": subscription, "event": event}


@frappe.whitelist(methods=["POST"])
@endpoint
def set_status(workspace, status, reason=None):
	operator = require_admin_reauthentication()
	subscription = billing.set_subscription_status(workspace, status, reason)
	event = billing.create_billing_event(
		workspace,
		"Adjustment",
		0,
		"Completed",
		provider_reference=f"Status {status} by {operator}: {(reason or 'No reason')[:100]}",
	)
	return {"subscription": subscription, "event": event}


@frappe.whitelist(methods=["POST"])
@endpoint
def top_up(workspace, tokens, amount=0, reference=None):
	require_admin_reauthentication()
	return billing.add_top_up(workspace, tokens, amount, reference)

@frappe.whitelist()
def download_document(workspace, document):
	check_workspace_access(workspace)
	if not frappe.db.exists("VerityAI Billing Document", {"name": document, "workspace": workspace}):
		frappe.throw("Billing document was not found.", frappe.DoesNotExistError)
	doc = frappe.get_doc("VerityAI Billing Document", document)
	from frappe.utils.pdf import get_pdf
	frappe.local.response.filename = f"{doc.document_number}.pdf"
	frappe.local.response.filecontent = get_pdf(doc.rendered_html)
	frappe.local.response.type = "download"


@frappe.whitelist(methods=["POST"])
@endpoint
def initiate_refund(workspace, payment, amount=None, reason=None):
	require_admin_reauthentication()
	return billing.initiate_refund(workspace, payment, amount, reason)


@frappe.whitelist(methods=["POST"])
@endpoint
def complete_refund(workspace, refund, provider_reference=None):
	require_admin_reauthentication()
	if not frappe.db.exists("VerityAI Billing Event", {"name": refund, "workspace": workspace, "event_type": "Refund"}):
		frappe.throw("Refund was not found.", frappe.DoesNotExistError)
	return billing.complete_refund(refund, provider_reference)


def _csv_safe(value):
	value = str(value or "")
	return "'" + value if value[:1] in {"=", "+", "-", "@"} else value


@frappe.whitelist()
def reconciliation_export(date_from=None, date_to=None):
	require_admin_reauthentication()
	filters = {}
	if date_from and date_to:
		filters["creation"] = ["between", [date_from, f"{date_to} 23:59:59"]]
	elif date_from:
		filters["creation"] = [">=", date_from]
	elif date_to:
		filters["creation"] = ["<=", f"{date_to} 23:59:59"]
	rows = frappe.get_all("VerityAI Billing Event", filters=filters, fields=["name", "workspace", "event_type", "amount", "currency", "status", "provider", "provider_reference", "gateway_reference", "gateway_status", "creation", "paid_on"], order_by="creation asc", limit_page_length=10000)
	output = io.StringIO(newline="")
	writer = csv.writer(output)
	fields = ["name", "workspace", "event_type", "amount", "currency", "status", "provider", "provider_reference", "gateway_reference", "gateway_status", "creation", "paid_on"]
	writer.writerow(fields)
	for row in rows:
		writer.writerow([_csv_safe(row.get(field)) for field in fields])
	frappe.local.response.filename = "verityai-billing-reconciliation.csv"
	frappe.local.response.filecontent = output.getvalue().encode("utf-8-sig")
	frappe.local.response.type = "download"
