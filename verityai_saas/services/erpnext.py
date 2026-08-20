import ipaddress
import socket
from urllib.parse import quote, urljoin, urlsplit

import frappe
import requests
from frappe.utils import cint, flt, now_datetime

from verityai_saas.services.entitlements import require_workspace_feature, workspace_context


TIMEOUT = (5, 25)
MAX_RESPONSE_BYTES = 5 * 1024 * 1024
MAX_PRODUCTS = 10000


def _public_https_url(value):
	value = str(value or "").strip().rstrip("/")
	parts = urlsplit(value)
	if parts.scheme != "https" or not parts.hostname or parts.username or parts.password or parts.port not in (None, 443) or parts.query or parts.fragment:
		frappe.throw("ERPNext URL must be a public HTTPS address on port 443.", frappe.ValidationError)
	try:
		addresses = {row[4][0] for row in socket.getaddrinfo(parts.hostname, 443, type=socket.SOCK_STREAM)}
	except OSError:
		frappe.throw("ERPNext hostname could not be resolved.", frappe.ValidationError)
	if not addresses or any(not ipaddress.ip_address(address).is_global for address in addresses):
		frappe.throw("ERPNext URL must resolve only to public addresses.", frappe.ValidationError)
	return value


def _connection(workspace, required=False):
	name = frappe.db.get_value("VerityAI ERPNext Connection", {"workspace": workspace}, "name")
	if not name:
		if required:
			frappe.throw("Connect ERPNext before using this action.", frappe.ValidationError)
		return None
	doc = frappe.get_doc("VerityAI ERPNext Connection", name)
	if required and not doc.enabled:
		frappe.throw("Enable the ERPNext connection before using this action.", frappe.ValidationError)
	return doc


def _password_present(doc, fieldname):
	try:
		return bool(doc.get_password(fieldname, raise_exception=False))
	except Exception:
		return False


def status(workspace):
	doc = _connection(workspace)
	context = workspace_context(workspace_name=workspace)
	available = bool(context and context.plan and context.plan.get("can_use_erpnext_integration"))
	return {
		"available": available,
		"configured": bool(doc and _password_present(doc, "api_key") and _password_present(doc, "api_secret")),
		"enabled": bool(doc and doc.enabled),
		"url": doc.erpnext_url if doc else "",
		"company": doc.company if doc else "",
		"selling_price_list": (doc.selling_price_list if doc else None) or "Standard Selling",
		"customer_group": (doc.customer_group if doc else None) or "All Customer Groups",
		"territory": (doc.territory if doc else None) or "All Territories",
		"sales_taxes_template": doc.sales_taxes_template if doc else "",
		"auto_sync_quotations": bool(doc and doc.auto_sync_quotations),
		"assistant_connector_enabled": bool(doc and doc.assistant_connector_enabled),
		"connection_status": (doc.connection_status if doc else None) or "Not Configured",
		"last_checked_on": doc.last_checked_on if doc else None,
		"last_product_sync_on": doc.last_product_sync_on if doc else None,
		"last_error": doc.last_error if doc else "",
	}


def configure(workspace, values):
	require_workspace_feature(workspace, "can_use_erpnext_integration", "ERPNext integration")
	values = values or {}
	doc = _connection(workspace) or frappe.get_doc({"doctype": "VerityAI ERPNext Connection", "workspace": workspace})
	doc.enabled = cint(values.get("enabled"))
	url = values.get("url") or doc.erpnext_url
	if doc.enabled or url:
		doc.erpnext_url = _public_https_url(url)
	api_key = str(values.get("api_key") or "").strip()
	api_secret = str(values.get("api_secret") or "").strip()
	if api_key:
		doc.api_key = api_key
	if api_secret:
		doc.api_secret = api_secret
	if doc.enabled and (not (api_key or _password_present(doc, "api_key")) or not (api_secret or _password_present(doc, "api_secret"))):
		frappe.throw("ERPNext API key and secret are required.", frappe.ValidationError)
	doc.company = str(values.get("company") or doc.company or "").strip() or None
	doc.selling_price_list = str(values.get("selling_price_list") or doc.selling_price_list or "Standard Selling").strip()
	doc.customer_group = str(values.get("customer_group") or doc.customer_group or "All Customer Groups").strip()
	doc.territory = str(values.get("territory") or doc.territory or "All Territories").strip()
	doc.sales_taxes_template = str(values.get("sales_taxes_template") or doc.sales_taxes_template or "").strip() or None
	doc.auto_sync_quotations = cint(values.get("auto_sync_quotations", 1))
	doc.assistant_connector_enabled = cint(values.get("assistant_connector_enabled"))
	doc.connection_status = "Not Checked" if doc.enabled else "Not Configured"
	doc.last_error = None
	if doc.is_new():
		doc.insert(ignore_permissions=True)
	else:
		doc.save(ignore_permissions=True)
	return status(workspace)


def _auth(doc):
	return f"token {doc.get_password('api_key')}:{doc.get_password('api_secret')}"


def _request(workspace, method, path, *, params=None, payload=None):
	doc = _connection(workspace, required=True)
	base = _public_https_url(doc.erpnext_url)
	if not path.startswith("/api/"):
		frappe.throw("Invalid ERPNext API path.", frappe.ValidationError)
	url = urljoin(base + "/", path.lstrip("/"))
	try:
		response = requests.request(
			method, url, params=params, json=payload,
			headers={"Authorization": _auth(doc), "Accept": "application/json", "Content-Type": "application/json"},
			timeout=TIMEOUT, allow_redirects=False, stream=True,
		)
		if 300 <= response.status_code < 400:
			raise frappe.ValidationError("ERPNext returned an unexpected redirect.")
		content = response.raw.read(MAX_RESPONSE_BYTES + 1, decode_content=True)
		if len(content) > MAX_RESPONSE_BYTES:
			raise frappe.ValidationError("ERPNext response exceeded the safe size limit.")
		if response.status_code < 200 or response.status_code >= 300:
			message = "ERPNext rejected the request."
			try:
				body = frappe.parse_json(content.decode("utf-8"))
				message = body.get("message") or body.get("exc_type") or message
			except Exception:
				pass
			raise frappe.ValidationError(f"{message} (HTTP {response.status_code})")
		try:
			return frappe.parse_json(content.decode("utf-8"))
		except Exception as error:
			raise frappe.ValidationError("ERPNext returned an unreadable response.") from error
	except requests.RequestException as error:
		raise frappe.ValidationError("ERPNext could not be reached. Check the URL, firewall and API user.") from error


def _mark_connection(workspace, state, error=None):
	doc = _connection(workspace)
	if not doc:
		return
	doc.db_set({"connection_status": state, "last_checked_on": now_datetime(), "last_error": str(error or "")[:500]}, update_modified=False)


def test_connection(workspace):
	require_workspace_feature(workspace, "can_use_erpnext_integration", "ERPNext integration")
	try:
		user = _request(workspace, "GET", "/api/method/frappe.auth.get_logged_user").get("message")
		companies = _request(workspace, "GET", "/api/resource/Company", params={"fields": '["name"]', "limit_page_length": 100}).get("data") or []
		connector = None
		connection = _connection(workspace, required=True)
		if connection.assistant_connector_enabled:
			connector = _request(workspace, "GET", "/api/method/verity_ai.api.connector.health").get("message") or {}
			if not connector.get("connector"):
				frappe.throw("The VerityAI ERPNext connector did not pass its health check.", frappe.ValidationError)
		_mark_connection(workspace, "Connected")
		return {"connected": True, "user": user, "companies": [row.get("name") for row in companies], "connector": connector}
	except Exception as error:
		_mark_connection(workspace, "Failed", error)
		raise


def _resource_rows(workspace, doctype, fields, filters=None):
	rows = []
	for start in range(0, MAX_PRODUCTS, 500):
		params = {"fields": frappe.as_json(fields), "limit_start": start, "limit_page_length": 500, "order_by": "modified asc"}
		if filters:
			params["filters"] = frappe.as_json(filters)
		page = _request(workspace, "GET", f"/api/resource/{quote(doctype, safe='')}", params=params).get("data") or []
		rows.extend(page)
		if len(page) < 500:
			break
	if len(rows) >= MAX_PRODUCTS:
		frappe.throw("ERPNext catalogue exceeds the 10,000 item sync limit. Narrow the catalogue before syncing.", frappe.ValidationError)
	return rows


def sync_products(workspace):
	require_workspace_feature(workspace, "can_use_erpnext_integration", "ERPNext integration")
	doc = _connection(workspace, required=True)
	items = _resource_rows(workspace, "Item", ["name", "item_code", "item_name", "description", "item_group", "stock_uom", "is_stock_item", "disabled"])
	prices = _resource_rows(workspace, "Item Price", ["item_code", "price_list", "currency", "price_list_rate", "selling"], filters=[["selling", "=", 1]])
	preferred = doc.selling_price_list or "Standard Selling"
	price_map = {}
	for row in prices:
		if row.get("price_list") == preferred:
			price_map[row.get("item_code")] = row
	from verityai_saas.services import commerce

	created = updated = 0
	for row in items:
		code = str(row.get("item_code") or row.get("name") or "").strip().upper()
		if not code:
			continue
		existing = frappe.db.get_value("VerityAI Product", {"workspace": workspace, "item_code": code}, "name")
		price = price_map.get(row.get("item_code")) or {}
		product = commerce.save_product(workspace, {
			"item_code": code, "item_name": row.get("item_name") or code,
			"description": row.get("description"), "item_group": row.get("item_group") or "Products",
			"stock_uom": row.get("stock_uom") or "Unit", "is_stock_item": cint(row.get("is_stock_item")),
			"standard_rate": flt(price.get("price_list_rate"), 2),
			"currency": price.get("currency") or frappe.db.get_value("VerityAI Workspace", workspace, "currency") or "USD",
			"active": int(not cint(row.get("disabled"))),
		}, product=existing)
		frappe.db.set_value("VerityAI Product", product.name, {"external_system": "ERPNext", "external_id": row.get("name") or row.get("item_code"), "last_synced_on": now_datetime()}, update_modified=False)
		updated += int(bool(existing))
		created += int(not existing)
	doc.db_set({"last_product_sync_on": now_datetime(), "connection_status": "Connected", "last_checked_on": now_datetime(), "last_error": None}, update_modified=False)
	return {"created": created, "updated": updated, "total": created + updated, "price_list": preferred}


def _find_or_create_customer(workspace, customer):
	if customer.external_system == "ERPNext" and customer.external_id:
		return customer.external_id
	filters = [["customer_name", "=", customer.customer_name]]
	rows = _resource_rows(workspace, "Customer", ["name", "customer_name"], filters=filters)
	if rows:
		name = rows[0]["name"]
	else:
		connection = _connection(workspace, required=True)
		payload = {"customer_name": customer.customer_name, "customer_type": customer.customer_type or "Company", "customer_group": connection.customer_group or "All Customer Groups", "territory": connection.territory or "All Territories"}
		name = (_request(workspace, "POST", "/api/resource/Customer", payload=payload).get("data") or {}).get("name")
	if not name:
		frappe.throw("ERPNext did not return a customer identifier.", frappe.ValidationError)
	frappe.db.set_value("VerityAI Customer", customer.name, {"external_system": "ERPNext", "external_id": name, "last_synced_on": now_datetime()}, update_modified=False)
	return name


def sync_quotation(workspace, quotation):
	require_workspace_feature(workspace, "can_use_erpnext_integration", "ERPNext integration")
	connection = _connection(workspace, required=True)
	from verityai_saas.services import commerce

	quote_doc = commerce.get_quotation(workspace, quotation)
	if quote_doc.status not in {"Approved", "Sent", "Accepted"}:
		frappe.throw("Approve the quotation before syncing it to ERPNext.", frappe.ValidationError)
	if quote_doc.external_system == "ERPNext" and quote_doc.external_id:
		return {"synced": True, "quotation": quote_doc.name, "erpnext_quotation": quote_doc.external_id, "already_synced": True}
	if flt(quote_doc.tax_rate) and not connection.sales_taxes_template:
		frappe.throw("Choose an ERPNext sales taxes and charges template before syncing a quotation with tax.", frappe.ValidationError)
	customer = frappe.get_doc("VerityAI Customer", quote_doc.customer)
	party = _find_or_create_customer(workspace, customer)
	payload = {
		"quotation_to": "Customer", "party_name": party,
		"transaction_date": str(quote_doc.transaction_date), "valid_till": str(quote_doc.valid_till) if quote_doc.valid_till else None,
		"currency": quote_doc.currency, "selling_price_list": connection.selling_price_list or quote_doc.price_list,
		"discount_amount": flt(quote_doc.discount_amount, 2),
		"items": [{"item_code": row.get("item_code"), "qty": flt(row.get("qty"), 4), "uom": row.get("uom"), "rate": flt(row.get("rate"), 2), "discount_percentage": flt(row.get("discount_percent"), 2), "description": row.get("description")} for row in quote_doc.get("items", [])],
	}
	if connection.company:
		payload["company"] = connection.company
	if connection.sales_taxes_template:
		payload["taxes_and_charges"] = connection.sales_taxes_template
	try:
		created = (_request(workspace, "POST", "/api/resource/Quotation", payload=payload).get("data") or {}).get("name")
		if not created:
			frappe.throw("ERPNext did not return a quotation identifier.", frappe.ValidationError)
		frappe.db.set_value("VerityAI Quotation", quotation, {"external_system": "ERPNext", "external_id": created, "sync_status": "Synced", "sync_error": None, "last_synced_on": now_datetime()}, update_modified=False)
		return {"synced": True, "quotation": quotation, "erpnext_quotation": created, "already_synced": False}
	except Exception as error:
		frappe.db.set_value("VerityAI Quotation", quotation, {"sync_status": "Failed", "sync_error": str(error)[:500], "last_synced_on": now_datetime()}, update_modified=False)
		raise


def auto_sync_quotation(workspace, quotation):
	doc = _connection(workspace)
	if not doc or not doc.enabled or not doc.auto_sync_quotations:
		return {"synced": False, "skipped": True}
	try:
		return sync_quotation(workspace, quotation)
	except Exception as error:
		frappe.log_error(title=f"ERPNext quotation sync failed: {quotation}", message=str(error))
		return {"synced": False, "error": str(error)}
