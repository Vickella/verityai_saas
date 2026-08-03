import json

import frappe
from frappe.utils import getdate, now_datetime, today

from verityai_saas.services import engine


def assign_plan(workspace_name, plan_name, status="Active"):
	workspace = frappe.get_doc("VerityAI Workspace", workspace_name)
	plan = frappe.get_doc("VerityAI Plan", plan_name)
	name = frappe.db.get_value("VerityAI Subscription", {"workspace": workspace_name}, "name", order_by="creation desc")
	if name:
		subscription = frappe.get_doc("VerityAI Subscription", name)
		subscription.update({"plan": plan.name, "status": status, "amount": plan.monthly_price, "currency": plan.currency})
		subscription.save(ignore_permissions=True)
	else:
		subscription = frappe.get_doc({"doctype": "VerityAI Subscription", "account": workspace.account, "workspace": workspace.name, "plan": plan.name, "status": status, "billing_cycle": "Monthly", "amount": plan.monthly_price, "currency": plan.currency}).insert(ignore_permissions=True)
	engine.apply_plan_limits(workspace_name, plan.name)
	engine.set_engine_active(workspace_name, status in {"Trial", "Active"})
	frappe.db.set_value("VerityAI Workspace", workspace_name, "status", "Trial" if status == "Trial" else "Active" if status == "Active" else "Suspended")
	return subscription.name


def set_subscription_status(workspace_name, status, reason=None):
	name = frappe.db.get_value("VerityAI Subscription", {"workspace": workspace_name}, "name", order_by="creation desc")
	if not name:
		frappe.throw("Subscription was not found.", frappe.DoesNotExistError)
	frappe.db.set_value("VerityAI Subscription", name, {"status": status, "suspension_reason": reason})
	active = status in {"Trial", "Active"}
	engine.set_engine_active(workspace_name, active)
	workspace_status = status if status in {"Trial", "Active", "Suspended", "Cancelled"} else "Suspended"
	frappe.db.set_value("VerityAI Workspace", workspace_name, "status", workspace_status)
	return name


def create_billing_event(workspace_name, event_type, amount=0, status="Pending", provider="Manual", provider_reference=None):
	workspace = frappe.get_doc("VerityAI Workspace", workspace_name)
	subscription = frappe.db.get_value("VerityAI Subscription", {"workspace": workspace_name}, "name", order_by="creation desc")
	wallet = frappe.db.get_value("VerityAI Usage Wallet", {"workspace": workspace_name}, ["tokens_used", "tokens_remaining", "estimated_ai_cost", "period_start", "period_end"], as_dict=True) or {}
	return frappe.get_doc({"doctype": "VerityAI Billing Event", "account": workspace.account, "workspace": workspace.name, "subscription": subscription, "event_type": event_type, "amount": amount, "currency": workspace.currency or "USD", "status": status, "provider": provider, "provider_reference": provider_reference, "usage_snapshot_json": json.dumps(wallet, default=str), "period_start": wallet.get("period_start"), "period_end": wallet.get("period_end"), "paid_on": now_datetime() if event_type == "Payment" and status == "Completed" else None}).insert(ignore_permissions=True).name


def check_trial_expiry():
	if not frappe.db.exists("DocType", "VerityAI Subscription"):
		return
	for row in frappe.get_all("VerityAI Subscription", filters={"status": "Trial", "trial_end": ["<", today()]}, fields=["workspace"]):
		set_subscription_status(row.workspace, "Expired", "Trial expired")
	frappe.db.commit()


def check_subscription_expiry():
	if not frappe.db.exists("DocType", "VerityAI Subscription"):
		return
	for row in frappe.get_all("VerityAI Subscription", filters={"status": "Active", "current_period_end": ["<", today()]}, fields=["workspace", "grace_period_end"]):
		if not row.grace_period_end or getdate(row.grace_period_end) < getdate(today()):
			set_subscription_status(row.workspace, "Expired", "Subscription period expired")
	frappe.db.commit()

