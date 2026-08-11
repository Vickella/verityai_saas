import frappe

from verityai_saas.api._response import endpoint
from verityai_saas.services import paynow
from verityai_saas.services.permissions import require_workspace_permission


@frappe.whitelist(methods=["POST"])
@endpoint
def start(workspace, plan, billing_cycle="Monthly", promotion_code=None):
	require_workspace_permission(workspace, "manage_billing")
	return paynow.initiate_checkout(workspace, plan, billing_cycle, promotion_code)


@frappe.whitelist(methods=["POST"])
@endpoint
def start_credit_top_up(workspace, credit_pack):
	require_workspace_permission(workspace, "manage_billing")
	return paynow.initiate_credit_checkout(workspace, credit_pack)


@frappe.whitelist(methods=["POST"])
@endpoint
def poll(workspace, payment):
	require_workspace_permission(workspace, "manage_billing")
	if not frappe.db.exists("VerityAI Billing Event", {"name": payment, "workspace": workspace, "provider": "Paynow"}):
		frappe.throw("Paynow payment was not found.", frappe.DoesNotExistError)
	return paynow.poll_payment(payment)


@frappe.whitelist(allow_guest=True, methods=["POST"])
@endpoint
def result(payment=None):
	raw_message = frappe.request.get_data(as_text=True) if getattr(frappe, "request", None) else ""
	return paynow.process_result(raw_message, payment)
