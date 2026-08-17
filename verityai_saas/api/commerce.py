import frappe

from verityai_saas.api._response import endpoint, json_value
from verityai_saas.services import commerce
from verityai_saas.services.permissions import require_workspace_permission


@frappe.whitelist()
@endpoint
def customers(workspace, search=None, status=None, limit=100):
	require_workspace_permission(workspace, "view_customers")
	return commerce.list_customers(workspace, search=search, status=status, limit=limit)


@frappe.whitelist(methods=["POST"])
@endpoint
def save_customer(workspace, values, customer=None):
	require_workspace_permission(workspace, "manage_customers")
	return commerce.save_customer(workspace, json_value(values, {}), customer=customer)


@frappe.whitelist(methods=["POST"])
@endpoint
def delete_customer(workspace, customer):
	require_workspace_permission(workspace, "manage_customers")
	return commerce.delete_customer(workspace, customer)


@frappe.whitelist()
@endpoint
def products(workspace, search=None, active=None, limit=100):
	require_workspace_permission(workspace, "view_catalog")
	return commerce.list_products(workspace, search=search, active=active, limit=limit)


@frappe.whitelist(methods=["POST"])
@endpoint
def save_product(workspace, values, product=None):
	require_workspace_permission(workspace, "manage_catalog")
	return commerce.save_product(workspace, json_value(values, {}), product=product)


@frappe.whitelist(methods=["POST"])
@endpoint
def delete_product(workspace, product):
	require_workspace_permission(workspace, "manage_catalog")
	return commerce.delete_product(workspace, product)


@frappe.whitelist()
def download_product_template(workspace):
	require_workspace_permission(workspace, "manage_catalog")
	frappe.local.response.filename = "VerityAI_Product_Import_Template.xlsx"
	frappe.local.response.filecontent = commerce.product_import_template()
	frappe.local.response.type = "binary"


@frappe.whitelist()
def export_products(workspace):
	require_workspace_permission(workspace, "view_catalog")
	frappe.local.response.filename = "VerityAI_Product_Catalogue.xlsx"
	frappe.local.response.filecontent = commerce.product_export(workspace)
	frappe.local.response.type = "binary"


@frappe.whitelist(methods=["POST"])
@endpoint
def import_products(workspace, update_existing=0):
	require_workspace_permission(workspace, "manage_catalog")
	upload = getattr(getattr(frappe, "request", None), "files", {}).get("file")
	if not upload or not str(upload.filename or "").lower().endswith(".xlsx"):
		frappe.throw("Upload an Excel .xlsx product workbook.", frappe.ValidationError)
	content = upload.read()
	if not content:
		frappe.throw("The uploaded workbook is empty.", frappe.ValidationError)
	if len(content) > 2 * 1024 * 1024:
		frappe.throw("The product workbook cannot exceed 2 MB.", frappe.ValidationError)
	return commerce.import_products(workspace, content, update_existing=bool(int(update_existing or 0)))


@frappe.whitelist()
@endpoint
def prices(workspace, product=None, price_list=None, limit=200):
	require_workspace_permission(workspace, "view_catalog")
	return commerce.list_prices(workspace, product=product, price_list=price_list, limit=limit)


@frappe.whitelist(methods=["POST"])
@endpoint
def save_price(workspace, values, price=None):
	require_workspace_permission(workspace, "manage_catalog")
	return commerce.save_price(workspace, json_value(values, {}), price=price)


@frappe.whitelist(methods=["POST"])
@endpoint
def delete_price(workspace, price):
	require_workspace_permission(workspace, "manage_catalog")
	return commerce.delete_price(workspace, price)


@frappe.whitelist()
@endpoint
def quotations(workspace, status=None, customer=None, limit=100):
	require_workspace_permission(workspace, "view_quotes")
	return commerce.list_quotations(workspace, status=status, customer=customer, limit=limit)


@frappe.whitelist()
@endpoint
def quotation(workspace, quotation):
	require_workspace_permission(workspace, "view_quotes")
	return commerce.get_quotation(workspace, quotation)


@frappe.whitelist(methods=["POST"])
@endpoint
def save_quotation(workspace, values, quotation=None):
	require_workspace_permission(workspace, "manage_quotes")
	return commerce.save_quotation(workspace, json_value(values, {}), quotation=quotation)


@frappe.whitelist(methods=["POST"])
@endpoint
def set_quotation_status(workspace, quotation, status):
	require_workspace_permission(workspace, "manage_quotes")
	return commerce.set_quotation_status(workspace, quotation, status)


@frappe.whitelist(methods=["POST"])
@endpoint
def convert_lead(workspace, lead, values=None):
	require_workspace_permission(workspace, "manage_customers")
	return commerce.convert_lead(workspace, lead, json_value(values, {}))


@frappe.whitelist()
@endpoint
def opportunities(workspace, stage=None, assigned_to=None, limit=200):
	require_workspace_permission(workspace, "view_customers")
	return commerce.list_opportunities(workspace, stage=stage, assigned_to=assigned_to, limit=limit)


@frappe.whitelist(methods=["POST"])
@endpoint
def save_opportunity(workspace, values, opportunity=None):
	require_workspace_permission(workspace, "manage_customers")
	return commerce.save_opportunity(workspace, json_value(values, {}), opportunity=opportunity)


@frappe.whitelist(methods=["POST"])
@endpoint
def set_opportunity_stage(workspace, opportunity, stage, lost_reason=None):
	require_workspace_permission(workspace, "manage_customers")
	return commerce.set_opportunity_stage(workspace, opportunity, stage, lost_reason=lost_reason)


@frappe.whitelist()
@endpoint
def appointments(workspace, status=None, from_date=None, to_date=None, limit=200):
	require_workspace_permission(workspace, "view_customers")
	return commerce.list_appointments(workspace, status=status, from_date=from_date, to_date=to_date, limit=limit)


@frappe.whitelist(methods=["POST"])
@endpoint
def save_appointment(workspace, values, appointment=None):
	require_workspace_permission(workspace, "manage_customers")
	return commerce.save_appointment(workspace, json_value(values, {}), appointment=appointment)


@frappe.whitelist(methods=["POST"])
@endpoint
def set_appointment_status(workspace, appointment, status, outcome=None):
	require_workspace_permission(workspace, "manage_customers")
	return commerce.set_appointment_status(workspace, appointment, status, outcome=outcome)


@frappe.whitelist()
@endpoint
def activities(workspace, lead=None, customer=None, opportunity=None, status=None, limit=200):
	require_workspace_permission(workspace, "view_customers")
	return commerce.list_activities(workspace, lead=lead, customer=customer, opportunity=opportunity, status=status, limit=limit)


@frappe.whitelist(methods=["POST"])
@endpoint
def save_activity(workspace, values):
	require_workspace_permission(workspace, "manage_customers")
	return commerce.save_activity(workspace, json_value(values, {}))


@frappe.whitelist(methods=["POST"])
@endpoint
def set_activity_status(workspace, activity, status):
	require_workspace_permission(workspace, "manage_customers")
	return commerce.set_activity_status(workspace, activity, status)


@frappe.whitelist()
def download_quotation(workspace, quotation):
	require_workspace_permission(workspace, "view_quotes")
	from frappe.utils.pdf import get_pdf

	frappe.local.response.filename = f"{quotation}.pdf"
	frappe.local.response.filecontent = get_pdf(commerce.quotation_html(workspace, quotation))
	frappe.local.response.type = "pdf"
