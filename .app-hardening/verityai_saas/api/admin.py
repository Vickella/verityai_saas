import re

import frappe
from frappe.utils import add_days, cint, flt, getdate, today

from verityai_saas.api._response import endpoint, json_value
from verityai_saas.services import paynow, platform_email
from verityai_saas.services.admin_reauth import require_admin_reauthentication
from verityai_saas.services.permissions import is_platform_admin, require_platform_admin



PLAN_CHECK_FIELDS = (
	"active", "can_remove_branding", "can_use_whatsapp_button", "can_use_whatsapp_ai",
	"can_use_email_notifications", "can_use_custom_smtp", "can_use_erpnext_integration",
	"can_use_quotation_workflow", "can_use_api_access", "can_bring_own_ai_provider_key",
)
PLAN_INT_FIELDS = (
	"trial_days", "max_workspaces", "max_assistants", "max_team_members", "monthly_token_limit",
	"max_tokens", "public_rate_limit_per_minute", "max_public_message_chars", "monthly_web_conversations",
	"monthly_whatsapp_messages", "monthly_email_sends", "max_knowledge_sources", "max_allowed_domains",
)
PLAN_CURRENCY_FIELDS = ("monthly_price", "annual_price")
PLAN_SAFE_FIELDS = (
	"name", "plan_name", "plan_code", "active", "currency", *PLAN_CURRENCY_FIELDS, *PLAN_INT_FIELDS,
	*PLAN_CHECK_FIELDS[1:], "support_level",
)


def _plan_data(plan):
	return {field: plan.get(field) for field in PLAN_SAFE_FIELDS}


def _apply_plan_values(plan, values, creating=False):
	values = json_value(values, {})
	if creating:
		plan_code = (values.get("plan_code") or "").strip().upper()
		if not re.fullmatch(r"[A-Z0-9][A-Z0-9_-]{1,39}", plan_code):
			frappe.throw("Plan code must be 2-40 uppercase letters, numbers, underscores, or hyphens.", frappe.ValidationError)
		plan.plan_code = plan_code
	plan_name = (values.get("plan_name") or plan.plan_name or "").strip()
	if not plan_name:
		frappe.throw("Plan name is required.", frappe.ValidationError)
	plan.plan_name = plan_name
	if "currency" in values:
		plan.currency = (values.get("currency") or "USD").strip().upper()
	if "support_level" in values:
		if values.get("support_level") not in {"Community", "Standard", "Priority"}:
			frappe.throw("Unsupported support level.", frappe.ValidationError)
		plan.support_level = values.get("support_level")
	for field in PLAN_CHECK_FIELDS:
		if field in values:
			setattr(plan, field, 1 if cint(values.get(field)) else 0)
	for field in PLAN_INT_FIELDS:
		if field in values:
			value = cint(values.get(field))
			if value < 0:
				frappe.throw(f"{field.replace('_', ' ').title()} cannot be negative.", frappe.ValidationError)
			setattr(plan, field, value)
	for field in PLAN_CURRENCY_FIELDS:
		if field in values:
			value = flt(values.get(field))
			if value < 0:
				frappe.throw(f"{field.replace('_', ' ').title()} cannot be negative.", frappe.ValidationError)
			setattr(plan, field, value)
	return plan

def _latest_by_workspace(doctype, workspace_names, fields):
	rows = frappe.get_all(
		doctype,
		filters={"workspace": ["in", workspace_names]},
		fields=fields,
		order_by="workspace asc, creation desc",
	)
	latest = {}
	for row in rows:
		latest.setdefault(row.workspace, row)
	return latest


def _counts_by_tenant(doctype, tenants, filters=None):
	if not tenants:
		return {}
	rows = frappe.get_all(
		doctype,
		filters={"tenant": ["in", tenants], **(filters or {})},
		fields=["tenant", "count(name) as total"],
		group_by="tenant",
	)
	return {row.tenant: row.total for row in rows}


@frappe.whitelist()
@endpoint
def dashboard():
	require_admin_reauthentication()
	workspaces = frappe.get_all(
		"VerityAI Workspace",
		fields=["name", "workspace_name", "business_name", "engine_tenant", "status", "setup_progress", "account", "currency"],
		order_by="creation desc",
		limit=500,
	)
	workspace_names = [row.name for row in workspaces]
	tenants = [row.engine_tenant for row in workspaces if row.engine_tenant]
	subscriptions = _latest_by_workspace(
		"VerityAI Subscription",
		workspace_names,
		["name", "workspace", "plan", "status", "billing_cycle", "trial_end", "current_period_end", "next_billing_date", "amount", "currency", "suspension_reason"],
	) if workspace_names else {}
	wallets = _latest_by_workspace(
		"VerityAI Usage Wallet",
		workspace_names,
		["name", "workspace", "opening_token_allowance", "top_up_tokens", "promotional_credits", "tokens_used", "tokens_remaining", "status", "period_start", "period_end"],
	) if workspace_names else {}
	lead_counts = _counts_by_tenant("AI Lead", tenants, {"status": "New"})
	alert_counts = _counts_by_tenant("AI Monitoring Alert", tenants, {"status": ["in", ["Open", "Acknowledged"]]})

	trial_cutoff = getdate(add_days(today(), 7))
	trial_expiring = []
	high_usage = []
	for workspace in workspaces:
		workspace["subscription"] = subscriptions.get(workspace.name)
		workspace["wallet"] = wallets.get(workspace.name)
		workspace["new_leads"] = lead_counts.get(workspace.engine_tenant, 0)
		workspace["open_alerts"] = alert_counts.get(workspace.engine_tenant, 0)
		subscription = workspace.subscription
		if subscription and subscription.status == "Trial" and subscription.trial_end and getdate(subscription.trial_end) <= trial_cutoff:
			trial_expiring.append({"workspace": workspace.name, "business_name": workspace.business_name, "trial_end": subscription.trial_end})
		wallet = workspace.wallet
		if wallet:
			allowance = int(wallet.opening_token_allowance or 0) + int(wallet.top_up_tokens or 0) + int(wallet.promotional_credits or 0)
			usage_percent = round((int(wallet.tokens_used or 0) / max(allowance, 1)) * 100, 1)
			workspace["usage_percent"] = usage_percent
			if usage_percent >= 80:
				high_usage.append({"workspace": workspace.name, "business_name": workspace.business_name, "usage_percent": usage_percent, "tokens_remaining": wallet.tokens_remaining})

	provider_failures = frappe.get_all(
		"AI Monitoring Alert",
		filters={"alert_type": "System", "status": ["in", ["Open", "Acknowledged"]]},
		fields=["name", "tenant", "severity", "status", "summary", "last_seen"],
		order_by="last_seen desc",
		limit=50,
	)
	workspace_by_tenant = {row.engine_tenant: row.name for row in workspaces if row.engine_tenant}
	provider_failures = [
		frappe._dict({**row, "workspace": workspace_by_tenant.get(row.tenant)})
		for row in provider_failures if workspace_by_tenant.get(row.tenant)
	]
	for row in provider_failures:
		row.pop("tenant", None)

	active_paid = [row for row in subscriptions.values() if row.status == "Active"]
	mrr = sum(flt(row.amount) / 12 if row.billing_cycle == "Annual" else flt(row.amount) for row in active_paid)
	paid_accounts = len(set(frappe.get_all(
		"VerityAI Billing Event", filters={"event_type": "Payment", "status": "Completed"},
		pluck="account",
	)))
	account_count = frappe.db.count("VerityAI Account")
	commercial_metrics = {
		"mrr": round(mrr, 2),
		"active_paid": len(active_paid),
		"trial_conversion_rate": round((paid_accounts / max(account_count, 1)) * 100, 1),
		"referrals_pending": frappe.db.count("VerityAI Referral Reward", {"status": "Pending"}),
		"referrals_granted": frappe.db.count("VerityAI Referral Reward", {"status": "Granted"}),
		"promotion_redemptions": frappe.db.count("VerityAI Promotion Redemption", {"status": "Granted"}),
	}

	return {
		"can_configure_platform": is_platform_admin(),
		"accounts": frappe.db.count("VerityAI Account"),
		"workspaces": workspaces,
		"active": sum(row.status in {"Trial", "Active"} for row in workspaces),
		"suspended": sum(row.status == "Suspended" for row in workspaces),
		"trials": sum(bool(row.subscription and row.subscription.status == "Trial") for row in workspaces),
		"plans": frappe.get_all(
			"VerityAI Plan",
			fields=list(PLAN_SAFE_FIELDS),
			order_by="monthly_price asc",
		),
		"recent_events": frappe.get_all(
			"VerityAI Billing Event",
			fields=["name", "workspace", "event_type", "amount", "currency", "status", "provider", "gateway_status", "gateway_reference", "creation"],
			order_by="creation desc",
			limit=50,
		),
		"high_usage": sorted(high_usage, key=lambda row: row["usage_percent"], reverse=True),
		"trial_expiring": sorted(trial_expiring, key=lambda row: row["trial_end"]),
		"failed_whatsapp": frappe.get_all(
			"VerityAI WhatsApp Setup",
			filters={"setup_status": "Failed"},
			fields=["workspace", "mode", "setup_status", "last_tested_on"],
			limit=100,
		),
		"provider_failures": provider_failures,
		"paynow": paynow.configuration_status(),
		"paynow_configured": paynow.checkout_enabled(),
		"support_email": platform_email.email_configuration_status(),
		"commercial_metrics": commercial_metrics,
	}


@frappe.whitelist(methods=["POST"])
@endpoint
def configure_paynow(values):
	"""Update the platform-wide Paynow gateway from the secured operator console."""
	require_platform_admin()
	require_admin_reauthentication()
	return paynow.configure(json_value(values, {}))


@frappe.whitelist(methods=["POST"])
@endpoint
def configure_support_email(values):
	"""Configure the platform sender through Frappe's encrypted Email Account."""
	require_platform_admin()
	require_admin_reauthentication()
	from verityai_saas.services.platform_email import configure_support_email as configure

	return configure(json_value(values, {}))

@frappe.whitelist(methods=["POST"])
@endpoint
def create_plan(values):
	require_admin_reauthentication()
	plan = _apply_plan_values(frappe.get_doc({"doctype": "VerityAI Plan"}), values, creating=True)
	plan.insert(ignore_permissions=True)
	return _plan_data(plan)


@frappe.whitelist(methods=["POST"])
@endpoint
def update_plan(plan, values):
	require_admin_reauthentication()
	if not frappe.db.exists("VerityAI Plan", plan):
		frappe.throw("Plan was not found.", frappe.DoesNotExistError)
	doc = _apply_plan_values(frappe.get_doc("VerityAI Plan", plan), values)
	doc.save(ignore_permissions=True)
	return _plan_data(doc)


@frappe.whitelist(methods=["POST"])
@endpoint
def archive_plan(plan):
	require_admin_reauthentication()
	if plan == "TRIAL" or frappe.db.get_value("VerityAI Plan", plan, "plan_code") == "TRIAL":
		frappe.throw("The default trial plan cannot be archived.", frappe.ValidationError)
	if not frappe.db.exists("VerityAI Plan", plan):
		frappe.throw("Plan was not found.", frappe.DoesNotExistError)
	frappe.db.set_value("VerityAI Plan", plan, "active", 0)
	return {"plan": plan, "active": 0}
