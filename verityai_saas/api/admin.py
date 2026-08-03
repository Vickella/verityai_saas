import frappe

from verityai_saas.api._response import endpoint
from verityai_saas.services.permissions import require_operator


@frappe.whitelist()
@endpoint
def dashboard():
	require_operator()
	workspaces = frappe.get_all("VerityAI Workspace", fields=["name", "workspace_name", "business_name", "engine_tenant", "status", "setup_progress", "account"], order_by="creation desc", limit=500)
	for workspace in workspaces:
		subscription = frappe.db.get_value("VerityAI Subscription", {"workspace": workspace.name}, ["plan", "status", "trial_end", "current_period_end"], as_dict=True)
		wallet = frappe.db.get_value("VerityAI Usage Wallet", {"workspace": workspace.name}, ["tokens_used", "tokens_remaining", "status"], as_dict=True)
		workspace["subscription"], workspace["wallet"] = subscription, wallet
		workspace["new_leads"] = frappe.db.count("AI Lead", {"tenant": workspace.engine_tenant, "status": "New"}) if workspace.engine_tenant else 0
		workspace["open_alerts"] = frappe.db.count("AI Monitoring Alert", {"tenant": workspace.engine_tenant, "status": ["in", ["Open", "Acknowledged"]]}) if workspace.engine_tenant else 0
	return {
		"accounts": frappe.db.count("VerityAI Account"),
		"workspaces": workspaces,
		"active": sum(row.status in {"Trial", "Active"} for row in workspaces),
		"suspended": sum(row.status == "Suspended" for row in workspaces),
		"failed_whatsapp": frappe.get_all("VerityAI WhatsApp Setup", filters={"setup_status": "Failed"}, fields=["workspace", "mode", "setup_status", "last_tested_on"], limit=100),
		"provider_failures": frappe.get_all("AI Monitoring Alert", filters={"alert_type": "System", "status": ["in", ["Open", "Acknowledged"]]}, fields=["name", "tenant", "severity", "summary", "last_seen"], order_by="last_seen desc", limit=50),
	}

