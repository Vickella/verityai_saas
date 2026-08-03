import frappe

from verityai_saas.services.permissions import require_operator


def get_context(context):
	require_operator()
	context.no_cache = 1
	context.title = "VerityAI Operator Dashboard"
	context.workspaces = frappe.get_all("VerityAI Workspace", fields=["name", "business_name", "status", "setup_progress", "engine_tenant"], order_by="creation desc", limit=500)
	for workspace in context.workspaces:
		workspace.subscription_status = frappe.db.get_value("VerityAI Subscription", {"workspace": workspace.name}, "status", order_by="creation desc")
		workspace.plan = frappe.db.get_value("VerityAI Subscription", {"workspace": workspace.name}, "plan", order_by="creation desc")
		workspace.tokens_used = frappe.db.get_value("VerityAI Usage Wallet", {"workspace": workspace.name}, "tokens_used") or 0
		workspace.open_alerts = frappe.db.count("AI Monitoring Alert", {"tenant": workspace.engine_tenant, "status": ["in", ["Open", "Acknowledged"]]}) if workspace.engine_tenant else 0
	context.accounts = frappe.db.count("VerityAI Account")
	context.suspended = sum(row.status == "Suspended" for row in context.workspaces)
	return context

