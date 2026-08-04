import json

import frappe
from frappe.utils import add_days, add_months, add_years, cint, flt, getdate, now_datetime, today

from verityai_saas.services import engine


SUBSCRIPTION_STATUSES = {"Trial", "Active", "Past Due", "Suspended", "Cancelled", "Expired"}
BILLING_CYCLES = {"Monthly", "Annual", "Manual"}
BILLING_EVENT_TYPES = {"Invoice", "Payment", "Credit", "Adjustment", "Top-Up", "Refund", "Subscription Activation"}
BILLING_EVENT_STATUSES = {"Pending", "Completed", "Failed", "Cancelled"}


def _validate_choice(value, allowed, label):
	if value not in allowed:
		frappe.throw(f"Invalid {label}.", frappe.ValidationError)
	return value


def _period_dates(status, billing_cycle, trial_days=14):
	start = getdate(today())
	if status == "Trial":
		return start, add_days(start, cint(trial_days or 14))
	if billing_cycle == "Annual":
		return start, add_years(start, 1)
	if billing_cycle == "Monthly":
		return start, add_months(start, 1)
	return start, None


def assign_plan(workspace_name, plan_name, status="Active", billing_cycle="Monthly"):
	_validate_choice(status, SUBSCRIPTION_STATUSES, "subscription status")
	_validate_choice(billing_cycle, BILLING_CYCLES, "billing cycle")
	workspace = frappe.get_doc("VerityAI Workspace", workspace_name)
	plan = frappe.get_doc("VerityAI Plan", plan_name)
	if not plan.active:
		frappe.throw("The selected plan is inactive.", frappe.ValidationError)
	period_start, period_end = _period_dates(status, billing_cycle, plan.trial_days)
	values = {
		"plan": plan.name,
		"status": status,
		"billing_cycle": billing_cycle,
		"amount": plan.annual_price if billing_cycle == "Annual" else plan.monthly_price,
		"currency": plan.currency,
		"current_period_start": period_start,
		"current_period_end": period_end,
		"next_billing_date": period_end,
	}
	if status == "Trial":
		values.update({"trial_start": period_start, "trial_end": period_end})
	name = frappe.db.get_value("VerityAI Subscription", {"workspace": workspace_name}, "name", order_by="creation desc")
	if name:
		subscription = frappe.get_doc("VerityAI Subscription", name)
		subscription.update(values)
		subscription.save(ignore_permissions=True)
	else:
		subscription = frappe.get_doc({"doctype": "VerityAI Subscription", "account": workspace.account, "workspace": workspace.name, **values}).insert(ignore_permissions=True)
	wallet_name = frappe.db.get_value("VerityAI Usage Wallet", {"workspace": workspace_name}, "name")
	if wallet_name:
		wallet = frappe.get_doc("VerityAI Usage Wallet", wallet_name)
		wallet_period_end = period_end if status == "Trial" else add_days(add_months(period_start, 1), -1)
		wallet.update({
			"subscription": subscription.name,
			"period_start": period_start,
			"period_end": wallet_period_end,
			"opening_token_allowance": cint(plan.monthly_token_limit),
			"tokens_remaining": max(cint(plan.monthly_token_limit) + cint(wallet.top_up_tokens) - cint(wallet.tokens_used), 0),
			"status": "Normal" if status in {"Trial", "Active"} else "Suspended",
		})
		wallet.save(ignore_permissions=True)
	engine.apply_plan_limits(workspace_name, plan.name)
	engine.set_engine_active(workspace_name, status in {"Trial", "Active"})
	frappe.db.set_value("VerityAI Workspace", workspace_name, "status", "Trial" if status == "Trial" else "Active" if status == "Active" else "Suspended")
	return subscription.name


def set_subscription_status(workspace_name, status, reason=None):
	_validate_choice(status, SUBSCRIPTION_STATUSES, "subscription status")
	subscription = frappe.db.get_value("VerityAI Subscription", {"workspace": workspace_name}, ["name", "grace_period_end"], as_dict=True, order_by="creation desc")
	if not subscription:
		frappe.throw("Subscription was not found.", frappe.DoesNotExistError)
	frappe.db.set_value("VerityAI Subscription", subscription.name, {"status": status, "suspension_reason": reason})
	grace_active = status == "Past Due" and subscription.grace_period_end and getdate(subscription.grace_period_end) >= getdate(today())
	active = status in {"Trial", "Active"} or grace_active
	engine.set_engine_active(workspace_name, active)
	workspace_status = "Active" if grace_active else status if status in {"Trial", "Active", "Suspended", "Cancelled"} else "Suspended"
	frappe.db.set_value("VerityAI Workspace", workspace_name, "status", workspace_status)
	wallet_name = frappe.db.get_value("VerityAI Usage Wallet", {"workspace": workspace_name}, "name")
	if wallet_name:
		wallet_status = "Normal" if active else "Suspended"
		frappe.db.set_value("VerityAI Usage Wallet", wallet_name, "status", wallet_status)
	return subscription.name


def create_billing_event(workspace_name, event_type, amount=0, status="Pending", provider="Manual", provider_reference=None):
	_validate_choice(event_type, BILLING_EVENT_TYPES, "billing event type")
	_validate_choice(status, BILLING_EVENT_STATUSES, "billing event status")
	amount = flt(amount)
	if amount < 0:
		frappe.throw("Billing event amount cannot be negative.", frappe.ValidationError)
	if event_type == "Payment" and status == "Completed" and provider == "Manual":
		if amount <= 0:
			frappe.throw("A completed manual payment must have a positive amount.", frappe.ValidationError)
		if not (provider_reference or "").strip():
			frappe.throw("A completed manual payment requires a reference.", frappe.ValidationError)
	workspace = frappe.get_doc("VerityAI Workspace", workspace_name)
	subscription = frappe.db.get_value("VerityAI Subscription", {"workspace": workspace_name}, "name", order_by="creation desc")
	wallet = frappe.db.get_value("VerityAI Usage Wallet", {"workspace": workspace_name}, ["tokens_used", "tokens_remaining", "estimated_ai_cost", "period_start", "period_end"], as_dict=True) or {}
	event = frappe.get_doc({"doctype": "VerityAI Billing Event", "account": workspace.account, "workspace": workspace.name, "subscription": subscription, "event_type": event_type, "amount": amount, "currency": workspace.currency or "USD", "status": status, "provider": provider, "provider_reference": provider_reference, "usage_snapshot_json": json.dumps(wallet, default=str), "period_start": wallet.get("period_start"), "period_end": wallet.get("period_end"), "paid_on": now_datetime() if event_type == "Payment" and status == "Completed" else None}).insert(ignore_permissions=True)
	if event_type == "Payment" and status == "Completed" and subscription:
		frappe.db.set_value("VerityAI Subscription", subscription, "last_payment_reference", provider_reference)
		from verityai_saas.services.billing_documents import ensure_receipt_for_payment
		ensure_receipt_for_payment(event.name)
	return event.name


def add_top_up(workspace_name, tokens, amount=0, provider_reference=None):
	tokens = cint(tokens)
	if tokens <= 0:
		frappe.throw("Top-up tokens must be greater than zero.", frappe.ValidationError)
	wallet_name = frappe.db.get_value("VerityAI Usage Wallet", {"workspace": workspace_name}, "name")
	if not wallet_name:
		frappe.throw("Usage wallet was not found.", frappe.DoesNotExistError)
	workspace = frappe.get_doc("VerityAI Workspace", workspace_name)
	wallet = frappe.get_doc("VerityAI Usage Wallet", wallet_name)
	event = create_billing_event(workspace_name, "Top-Up", amount, "Completed", provider_reference=provider_reference)
	from verityai_saas.services.billing_documents import ensure_document
	ensure_document(event, "Receipt", status="Paid")
	transaction = frappe.get_doc({
		"doctype": "VerityAI Usage Transaction",
		"workspace": workspace_name,
		"engine_tenant": workspace.engine_tenant,
		"transaction_type": "Top-Up",
		"total_tokens": tokens,
		"billable_amount": flt(amount),
		"period": getdate(today()).strftime("%Y-%m"),
	}).insert(ignore_permissions=True)
	wallet.top_up_tokens = cint(wallet.top_up_tokens) + tokens
	wallet.tokens_remaining = cint(wallet.tokens_remaining) + tokens
	if wallet.status in {"Warning", "Exhausted"} and wallet.tokens_remaining > 0:
		wallet.status = "Normal"
	wallet.save(ignore_permissions=True)
	return {"event": event, "transaction": transaction.name, "wallet": wallet.name}


def roll_usage_periods():
	if not frappe.db.exists("DocType", "VerityAI Usage Wallet"):
		return
	current_date = getdate(today())
	for row in frappe.get_all(
		"VerityAI Usage Wallet",
		filters={"period_end": ["<", current_date]},
		fields=["name", "workspace", "period_end"],
	):
		plan_name = frappe.db.get_value(
			"VerityAI Subscription",
			{"workspace": row.workspace, "status": "Active"},
			"plan",
			order_by="creation desc",
		)
		if not plan_name:
			continue
		allowance = cint(frappe.db.get_value("VerityAI Plan", plan_name, "monthly_token_limit"))
		period_start = add_days(getdate(row.period_end), 1)
		period_end = add_days(add_months(period_start, 1), -1)
		while period_end < current_date:
			period_start = add_days(period_end, 1)
			period_end = add_days(add_months(period_start, 1), -1)
		frappe.db.set_value("VerityAI Usage Wallet", row.name, {
			"period_start": period_start,
			"period_end": period_end,
			"opening_token_allowance": allowance,
			"top_up_tokens": 0,
			"tokens_used": 0,
			"tokens_remaining": allowance,
			"status": "Normal",
		})
	frappe.db.commit()

def check_trial_expiry():
	if not frappe.db.exists("DocType", "VerityAI Subscription"):
		return
	for row in frappe.get_all("VerityAI Subscription", filters={"status": "Trial", "trial_end": ["<", today()]}, fields=["workspace"]):
		set_subscription_status(row.workspace, "Expired", "Trial expired")
	frappe.db.commit()


def check_subscription_expiry():
	if not frappe.db.exists("DocType", "VerityAI Subscription"):
		return
	current_date = getdate(today())
	for row in frappe.get_all("VerityAI Subscription", filters={"status": "Active", "current_period_end": ["<", current_date]}, fields=["name", "workspace", "grace_period_end"]):
		grace_end = getdate(row.grace_period_end) if row.grace_period_end else add_days(current_date, 7)
		frappe.db.set_value("VerityAI Subscription", row.name, "grace_period_end", grace_end)
		set_subscription_status(row.workspace, "Past Due", f"Payment grace period ends {grace_end}")
	for row in frappe.get_all("VerityAI Subscription", filters={"status": "Past Due", "grace_period_end": ["<", current_date]}, fields=["workspace"]):
		set_subscription_status(row.workspace, "Expired", "Payment grace period expired")
	frappe.db.commit()


def send_payment_reminders():
	from verityai_saas.services.notifications import send_notification

	current_date = getdate(today())
	for row in frappe.get_all("VerityAI Subscription", filters={"status": ["in", ["Trial", "Active", "Past Due"]]}, fields=["name", "workspace", "status", "next_billing_date", "grace_period_end", "amount", "currency"]):
		due = getdate(row.next_billing_date) if row.next_billing_date else None
		grace = getdate(row.grace_period_end) if row.grace_period_end else None
		if row.status == "Active" and (not due or due > add_days(current_date, 3)):
			continue
		if frappe.db.exists("VerityAI Email Delivery Log", {"workspace": row.workspace, "notification_type": "Payment Reminder", "reference_name": row.name, "creation": [">=", current_date]}):
			continue
		if row.status == "Past Due":
			message = f"Your payment is past due. The recovery grace period ends {grace or 'soon'}."
		elif row.status == "Trial":
			message = f"Your VerityAI trial ends on {due}. Choose a paid plan to avoid interruption."
		else:
			message = f"Your {row.currency or ''} {flt(row.amount):.2f} subscription payment is due on {due}."
		send_notification(row.workspace, "Payment Reminder", "VerityAI payment reminder", message, "VerityAI Subscription", row.name)
	frappe.db.commit()


def initiate_refund(workspace_name, payment_event, amount=None, reason=None):
	if not frappe.db.exists("VerityAI Billing Event", {"name": payment_event, "workspace": workspace_name, "event_type": "Payment", "status": "Completed"}):
		frappe.throw("Completed payment was not found.", frappe.DoesNotExistError)
	payment = frappe.get_doc("VerityAI Billing Event", payment_event)
	amount = flt(amount if amount not in (None, "") else payment.amount)
	completed = frappe.get_all("VerityAI Billing Event", filters={"workspace": workspace_name, "event_type": "Refund", "gateway_reference": payment.name, "status": ["in", ["Pending", "Completed"]]}, pluck="amount")
	remaining = max(flt(payment.amount) - sum(flt(value) for value in completed), 0)
	if amount <= 0 or amount > remaining:
		frappe.throw(f"Refund amount must be greater than zero and no more than {remaining:.2f}.", frappe.ValidationError)
	refund = create_billing_event(workspace_name, "Refund", amount, "Pending", provider=payment.provider or "Manual", provider_reference=f"Refund requested for {payment.name}: {(reason or 'No reason supplied')[:200]}")
	frappe.db.set_value("VerityAI Billing Event", refund, {"gateway_reference": payment.name, "gateway_status": "Refund Requested"})
	return {"refund": refund, "status": "Pending", "remaining_refundable": remaining - amount}


def complete_refund(refund_event, provider_reference=None):
	if not frappe.db.exists("VerityAI Billing Event", {"name": refund_event, "event_type": "Refund", "status": "Pending"}):
		frappe.throw("Pending refund was not found.", frappe.DoesNotExistError)
	refund = frappe.get_doc("VerityAI Billing Event", refund_event)
	frappe.db.set_value("VerityAI Billing Event", refund.name, {"status": "Completed", "gateway_status": "Refunded", "paid_on": now_datetime(), "provider_reference": provider_reference or refund.provider_reference})
	from verityai_saas.services.billing_documents import ensure_refund_confirmation
	ensure_refund_confirmation(refund.name)
	return {"refund": refund.name, "status": "Completed"}