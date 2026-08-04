import frappe
from frappe.utils import add_days, getdate, today

from verityai_saas.api._response import endpoint
from verityai_saas.services import paynow
from verityai_saas.services.permissions import require_operator


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
	require_operator()
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
		["name", "workspace", "opening_token_allowance", "top_up_tokens", "tokens_used", "tokens_remaining", "status", "period_start", "period_end"],
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
			allowance = int(wallet.opening_token_allowance or 0) + int(wallet.top_up_tokens or 0)
			usage_percent = round((int(wallet.tokens_used or 0) / max(allowance, 1)) * 100, 1)
			workspace["usage_percent"] = usage_percent
			if usage_percent >= 80:
				high_usage.append({"workspace": workspace.name, "business_name": workspace.business_name, "usage_percent": usage_percent, "tokens_remaining": wallet.tokens_remaining})

	return {
		"accounts": frappe.db.count("VerityAI Account"),
		"workspaces": workspaces,
		"active": sum(row.status in {"Trial", "Active"} for row in workspaces),
		"suspended": sum(row.status == "Suspended" for row in workspaces),
		"trials": sum(bool(row.subscription and row.subscription.status == "Trial") for row in workspaces),
		"plans": frappe.get_all(
			"VerityAI Plan",
			filters={"active": 1},
			fields=["name", "plan_name", "plan_code", "currency", "monthly_price", "annual_price", "monthly_token_limit"],
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
		"provider_failures": frappe.get_all(
			"AI Monitoring Alert",
			filters={"alert_type": "System", "status": ["in", ["Open", "Acknowledged"]]},
			fields=["name", "tenant", "severity", "summary", "last_seen"],
			order_by="last_seen desc",
			limit=50,
		),
		"paynow_configured": paynow.is_configured(),
	}