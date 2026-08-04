import frappe

from verityai_saas.api._response import endpoint
from verityai_saas.services import billing, paynow
from verityai_saas.services.permissions import check_workspace_access, require_operator


@frappe.whitelist()
@endpoint
def get(workspace):
	check_workspace_access(workspace)
	return {
		"subscription": frappe.get_all("VerityAI Subscription", filters={"workspace": workspace}, fields=["name", "plan", "status", "billing_cycle", "trial_end", "current_period_end", "next_billing_date", "amount", "currency"], order_by="creation desc", limit=1),
		"wallet": frappe.db.get_value("VerityAI Usage Wallet", {"workspace": workspace}, ["tokens_used", "tokens_remaining", "status", "estimated_ai_cost"], as_dict=True),
		"events": frappe.get_all("VerityAI Billing Event", filters={"workspace": workspace}, fields=["name", "event_type", "amount", "currency", "status", "provider", "gateway_status", "gateway_reference", "creation", "paid_on"], order_by="creation desc", limit=50),
		"plans": frappe.get_all("VerityAI Plan", filters={"active": 1}, fields=["name", "plan_name", "plan_code", "monthly_price", "annual_price", "currency", "monthly_token_limit"], order_by="monthly_price asc"),
		"paynow_configured": paynow.is_configured(),
	}


@frappe.whitelist(methods=["POST"])
@endpoint
def manual_event(workspace, event_type, amount=0, status="Pending", reference=None):
	require_operator()
	return {"event": billing.create_billing_event(workspace, event_type, amount, status, provider_reference=reference)}


@frappe.whitelist(methods=["POST"])
@endpoint
def assign_plan(workspace, plan, status="Active", billing_cycle="Monthly"):
	require_operator()
	return {"subscription": billing.assign_plan(workspace, plan, status, billing_cycle)}


@frappe.whitelist(methods=["POST"])
@endpoint
def set_status(workspace, status, reason=None):
	require_operator()
	return {"subscription": billing.set_subscription_status(workspace, status, reason)}


@frappe.whitelist(methods=["POST"])
@endpoint
def top_up(workspace, tokens, amount=0, reference=None):
	require_operator()
	return billing.add_top_up(workspace, tokens, amount, reference)