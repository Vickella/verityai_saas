import frappe
from frappe.utils import now_datetime

from verityai_saas.services.engine import get_workspace_engine_tenant


def sync_workspace_usage(workspace_name):
	tenant = get_workspace_engine_tenant(workspace_name)
	logs = frappe.get_all("AI Usage Log", filters={"tenant": tenant}, fields=["name", "platform", "input_tokens", "output_tokens", "total_tokens", "estimated_cost", "status", "creation"], order_by="creation asc")
	created = 0
	for row in logs:
		if frappe.db.exists("VerityAI Usage Transaction", {"ai_usage_log": row.name}):
			continue
		frappe.get_doc({"doctype": "VerityAI Usage Transaction", "workspace": workspace_name, "engine_tenant": tenant, "ai_usage_log": row.name, "transaction_type": "Blocked" if row.status == "Blocked" else "Usage", "platform": row.platform, "input_tokens": row.input_tokens or 0, "output_tokens": row.output_tokens or 0, "total_tokens": row.total_tokens or 0, "estimated_cost": row.estimated_cost or 0, "period": row.creation.strftime("%Y-%m")}).insert(ignore_permissions=True)
		created += 1
	wallet_name = frappe.db.get_value("VerityAI Usage Wallet", {"workspace": workspace_name}, "name")
	if wallet_name:
		wallet = frappe.get_doc("VerityAI Usage Wallet", wallet_name)
		totals = frappe.db.sql("""select coalesce(sum(total_tokens),0), coalesce(sum(estimated_cost),0) from `tabVerityAI Usage Transaction` where workspace=%s and transaction_type='Usage' and creation between %s and %s""", (workspace_name, wallet.period_start, f"{wallet.period_end} 23:59:59"))[0]
		wallet.tokens_used = int(totals[0] or 0)
		wallet.tokens_remaining = max(int(wallet.opening_token_allowance or 0) + int(wallet.top_up_tokens or 0) - wallet.tokens_used, 0)
		wallet.estimated_ai_cost = totals[1] or 0
		percent = (wallet.tokens_used / max(int(wallet.opening_token_allowance or 0) + int(wallet.top_up_tokens or 0), 1)) * 100
		wallet.status = "Exhausted" if wallet.tokens_remaining <= 0 else "Warning" if percent >= 80 else "Normal"
		wallet.last_synced_from_usage_logs = now_datetime()
		wallet.save(ignore_permissions=True)
	return {"created": created, "wallet": wallet_name}


def sync_all_usage():
	if not frappe.db.exists("DocType", "VerityAI Workspace"):
		return
	for workspace in frappe.get_all("VerityAI Workspace", filters={"engine_tenant": ["is", "set"]}, pluck="name"):
		try:
			sync_workspace_usage(workspace)
		except Exception:
			frappe.log_error(title=f"VerityAI Usage Sync: {workspace}", message=frappe.get_traceback())
	frappe.db.commit()

