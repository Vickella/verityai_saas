import frappe

from verityai_saas.api._response import endpoint
from verityai_saas.services import engine
from verityai_saas.services.permissions import check_workspace_access
from verityai_saas.services.usage import sync_workspace_usage


@frappe.whitelist()
@endpoint
def get(workspace, from_date=None, to_date=None):
	check_workspace_access(workspace)
	sync_workspace_usage(workspace)
	data = engine.get_workspace_usage(workspace, from_date, to_date)
	data["wallet"] = frappe.db.get_value("VerityAI Usage Wallet", {"workspace": workspace}, ["opening_token_allowance", "top_up_tokens", "tokens_used", "tokens_remaining", "status", "period_start", "period_end"], as_dict=True)
	return data

