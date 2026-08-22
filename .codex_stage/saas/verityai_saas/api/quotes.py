import frappe

from verityai_saas.api._response import endpoint, json_value
from verityai_saas.services import commerce
from verityai_saas.services.permissions import require_workspace_permission


@frappe.whitelist()
@endpoint
def list_requests(workspace, status=None, limit=100):
	require_workspace_permission(workspace, "approve_quotes")
	return commerce.list_quotations(workspace, status=status, limit=limit)


@frappe.whitelist()
@endpoint
def detail(workspace, quotation_request):
	require_workspace_permission(workspace, "approve_quotes")
	return commerce.get_quotation(workspace, quotation_request)


@frappe.whitelist(methods=["POST"])
@endpoint
def update(workspace, quotation_request, values):
	require_workspace_permission(workspace, "approve_quotes")
	values = json_value(values, {})
	# The review UI may leave an AI-captured line description untouched. Preserve
	# that captured scope instead of replacing it with the generic product text.
	existing = commerce.get_quotation(workspace, quotation_request)
	for index, item in enumerate(values.get("items") or []):
		if not item.get("description") and index < len(existing["items"]):
			item["description"] = existing["items"][index].get("description")
	return commerce.save_quotation(workspace, values, quotation=quotation_request)


@frappe.whitelist(methods=["POST"])
@endpoint
def approve(workspace, quotation_request, notes=None):
	require_workspace_permission(workspace, "approve_quotes")
	if notes:
		quote = commerce.get_quotation(workspace, quotation_request)
		values = {
			"customer": quote.customer, "transaction_date": quote.transaction_date,
			"valid_till": quote.valid_till, "price_list": quote.price_list,
			"currency": quote.currency, "discount_amount": quote.discount_amount,
			"tax_rate": quote.tax_rate, "notes": notes, "items": quote["items"],
		}
		commerce.save_quotation(workspace, values, quotation=quotation_request)
	return commerce.approve_and_send_quotation(workspace, quotation_request)


@frappe.whitelist(methods=["POST"])
@endpoint
def reject(workspace, quotation_request, reason=None):
	require_workspace_permission(workspace, "approve_quotes")
	quote = commerce.get_quotation(workspace, quotation_request)
	if quote.status != "Pending Approval":
		frappe.throw("Only a pending quotation can be rejected.", frappe.ValidationError)
	if reason:
		values = {
			"customer": quote.customer, "transaction_date": quote.transaction_date,
			"valid_till": quote.valid_till, "price_list": quote.price_list,
			"currency": quote.currency, "discount_amount": quote.discount_amount,
			"tax_rate": quote.tax_rate, "notes": reason, "items": quote["items"],
		}
		commerce.save_quotation(workspace, values, quotation=quotation_request)
	return commerce.set_quotation_status(workspace, quotation_request, "Rejected")
