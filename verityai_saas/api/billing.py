import frappe

from verityai_saas.api._response import endpoint
from verityai_saas.services import billing
from verityai_saas.services.permissions import check_workspace_access, require_operator, require_workspace_permission


@frappe.whitelist()
@endpoint
def get(workspace):
	check_workspace_access(workspace)
	return {
		"subscription": frappe.get_all("VerityAI Subscription", filters={"workspace": workspace}, fields=["name", "plan", "status", "billing_cycle", "trial_end", "current_period_end", "next_billing_date", "amount", "currency"], order_by="creation desc", limit=1),
		"wallet": frappe.db.get_value("VerityAI Usage Wallet", {"workspace": workspace}, ["tokens_used", "tokens_remaining", "status", "estimated_ai_cost"], as_dict=True),
		"events": frappe.get_all("VerityAI Billing Event", filters={"workspace": workspace}, fields=["name", "event_type", "amount", "currency", "status", "provider_reference", "creation", "paid_on"], order_by="creation desc", limit=50),
		"upgrade_available": False,
	}


@frappe.whitelist()
@endpoint
def manual_event(workspace, event_type, amount=0, status="Pending", reference=None):
	require_workspace_permission(workspace, "manage_billing")
	return {"event": billing.create_billing_event(workspace, event_type, amount, status, provider_reference=reference)}


@frappe.whitelist()
@endpoint
def assign_plan(workspace, plan, status="Active"):
	require_operator()
	return {"subscription": billing.assign_plan(workspace, plan, status)}

