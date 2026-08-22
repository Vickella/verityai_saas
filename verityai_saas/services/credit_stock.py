import ipaddress
import socket
from decimal import Decimal, InvalidOperation, ROUND_FLOOR
from urllib.parse import quote, urljoin, urlsplit

import frappe
import requests
from frappe.utils import cint, flt, now_datetime, nowdate


LEDGER = "VerityAI Credit Stock Ledger"
SETTINGS = "VerityAI ERPNext Accounting Settings"
TIMEOUT = (5, 25)
MAX_CREDITS = 9_000_000_000_000_000
DEFAULT_PROVIDER_MODEL = "gpt-4.1-mini"
MILLION = Decimal("1000000")

# OpenAI's published blended price for GPT-4.1 mini is USD 0.42 per
# one million tokens. Keep provider pricing server-side so an operator or
# browser cannot accidentally overstate the credit stock received.
PROVIDER_BLENDED_USD_PER_MILLION = {
	"gpt-4.1-mini": Decimal("0.42"),
}


def calculate_credits(monetary_value, credits_per_currency_unit):
	"""Convert provider spend to whole credits without binary floating-point drift."""
	try:
		amount = Decimal(str(monetary_value or 0))
		rate = Decimal(str(credits_per_currency_unit or 0))
	except (InvalidOperation, ValueError, TypeError):
		frappe.throw("Enter a valid purchase amount and provider rate.", frappe.ValidationError)
	if amount <= 0:
		frappe.throw("Purchase amount must be greater than zero.", frappe.ValidationError)
	if rate <= 0:
		frappe.throw("Provider credits per currency unit must be greater than zero.", frappe.ValidationError)
	credits = int((amount * rate).to_integral_value(rounding=ROUND_FLOOR))
	if credits <= 0 or credits > MAX_CREDITS:
		frappe.throw("Calculated credits are outside the supported range.", frappe.ValidationError)
	return credits


def provider_pricing(model=None):
	"""Return the controlled token conversion for the configured AI model."""
	configured_model = str(model or "").strip()
	if not configured_model and frappe.db.exists("DocType", "VerityAI Platform Settings"):
		configured_model = str(frappe.get_single("VerityAI Platform Settings").get("ai_model") or "").strip()
	configured_model = configured_model or DEFAULT_PROVIDER_MODEL
	normalized = configured_model.lower()
	pricing_model = next(
		(key for key in PROVIDER_BLENDED_USD_PER_MILLION if normalized == key or normalized.startswith(f"{key}-")),
		None,
	)
	if not pricing_model:
		frappe.throw(
			f"Automatic provider credit conversion is not configured for {configured_model}.",
			frappe.ValidationError,
		)
	blended_cost = PROVIDER_BLENDED_USD_PER_MILLION[pricing_model]
	credits_per_usd = MILLION / blended_cost
	return {
		"model": configured_model,
		"pricing_model": pricing_model,
		"currency": "USD",
		"blended_usd_per_million": float(blended_cost),
		"credits_per_usd": float(credits_per_usd),
	}


def calculate_provider_credits(monetary_value, model=None):
	"""Calculate whole provider credits from USD spend using controlled pricing."""
	try:
		amount = Decimal(str(monetary_value or 0))
	except (InvalidOperation, ValueError, TypeError):
		frappe.throw("Enter a valid purchase amount.", frappe.ValidationError)
	if amount <= 0:
		frappe.throw("Purchase amount must be greater than zero.", frappe.ValidationError)
	pricing = provider_pricing(model)
	cost = Decimal(str(pricing["blended_usd_per_million"]))
	credits = int((amount * MILLION / cost).to_integral_value(rounding=ROUND_FLOOR))
	if credits <= 0 or credits > MAX_CREDITS:
		frappe.throw("Calculated credits are outside the supported range.", frappe.ValidationError)
	return credits


def _password_present(doc, fieldname):
	try:
		return bool(doc.get_password(fieldname, raise_exception=False))
	except Exception:
		return False


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


def _last_entry(lock=False):
	if not frappe.db.exists("DocType", LEDGER):
		return None
	rows = frappe.db.sql(
		f"select name from `tab{LEDGER}` order by posting_datetime desc, creation desc limit 1" + (" for update" if lock else ""),
		as_dict=True,
	)
	return frappe.get_doc(LEDGER, rows[0].name) if rows else None


def summary(limit=100):
	last = _last_entry()
	aggregates = frappe.db.sql(
		f"""select
			coalesce(sum(case when direction='Receipt' then credits else 0 end), 0) receipts,
			coalesce(sum(case when direction='Issue' then credits else 0 end), 0) issues,
			coalesce(sum(revenue), 0) revenue,
			coalesce(sum(cogs), 0) cogs,
			coalesce(sum(gross_profit), 0) gross_profit
		from `tab{LEDGER}`""",
		as_dict=True,
	)[0] if frappe.db.exists("DocType", LEDGER) else frappe._dict()
	settings = frappe.get_single(SETTINGS) if frappe.db.exists("DocType", SETTINGS) else frappe._dict()
	balance_credits = cint(last.balance_credits) if last else 0
	balance_value = flt(last.balance_value, 2) if last else 0
	average_unit_cost = (balance_value / balance_credits) if balance_credits > 0 else 0
	plans = []
	if frappe.db.exists("DocType", "VerityAI Plan"):
		for plan in frappe.get_all(
			"VerityAI Plan",
			filters={"active": 1, "monthly_price": [">", 0]},
			fields=["name", "plan_name", "currency", "monthly_price", "monthly_token_limit"],
			order_by="monthly_price asc",
		):
			credits = cint(plan.monthly_token_limit)
			estimated_cogs = flt(credits * average_unit_cost, 2)
			plans.append({
				**plan,
				"estimated_cogs": estimated_cogs,
				"estimated_gross_profit": flt(plan.monthly_price - estimated_cogs, 2),
				"credits_after_sale": balance_credits - credits,
			})
	pricing = provider_pricing()
	return {
		"balance_credits": balance_credits,
		"balance_value": balance_value,
		"average_unit_cost": average_unit_cost,
		"received_credits": cint(aggregates.get("receipts")), "allocated_credits": cint(aggregates.get("issues")),
		"revenue": flt(aggregates.get("revenue"), 2), "cogs": flt(aggregates.get("cogs"), 2),
		"gross_profit": flt(aggregates.get("gross_profit"), 2),
		"low_stock": bool(last and cint(last.balance_credits) < 0),
		"cost_basis_available": bool(balance_credits > 0 and balance_value > 0),
		"purchase_rate": flt(pricing["credits_per_usd"], 6),
		"provider_pricing": pricing,
		"plan_economics": plans,
		"ledger": frappe.get_all(LEDGER, fields=["name", "posting_datetime", "entry_type", "direction", "credits", "unit_cost", "inventory_value", "revenue", "cogs", "gross_profit", "balance_credits", "balance_value", "currency", "workspace", "billing_event", "reference", "erpnext_status", "erpnext_journal_entry", "erpnext_error"], order_by="posting_datetime desc, creation desc", limit=cint(limit or 100)) if frappe.db.exists("DocType", LEDGER) else [],
		"erpnext": {
			"enabled": bool(settings.get("enabled")), "auto_post": bool(settings.get("auto_post")),
			"configured": bool(settings.get("erpnext_url") and _password_present(settings, "api_key") and _password_present(settings, "api_secret")),
			"url": settings.get("erpnext_url") or "", "company": settings.get("company") or "", "currency": settings.get("currency") or "USD",
			"receivable_account": settings.get("receivable_account") or "", "sales_account": settings.get("sales_account") or "",
			"inventory_account": settings.get("inventory_account") or "", "cogs_account": settings.get("cogs_account") or "",
			"cost_center": settings.get("cost_center") or "", "connection_status": settings.get("connection_status") or "Not Configured",
			"last_checked_on": settings.get("last_checked_on"), "last_error": settings.get("last_error") or "",
		},
	}


def record_purchase(monetary_value, currency="USD", reference=None, notes=None, entry_type="Purchase"):
	if entry_type not in {"Purchase", "Opening Balance"}:
		frappe.throw("Invalid credit receipt type.", frappe.ValidationError)
	currency = str(currency or "USD").strip().upper()
	if currency != "USD":
		frappe.throw("Provider credit purchases must be recorded in USD.", frappe.ValidationError)
	pricing = provider_pricing()
	credits = calculate_provider_credits(monetary_value, pricing["model"])
	settings = frappe.get_single(SETTINGS)
	settings.credits_per_currency_unit = flt(pricing["credits_per_usd"], 6)
	settings.save(ignore_permissions=True)
	return record_entry(
		entry_type,
		credits,
		monetary_value,
		"Receipt",
		"USD",
		reference=reference,
		notes=notes,
		source_key=(
			f"provider:{entry_type.lower().replace(' ', '-')}:USD:{str(reference).strip()}"
			if reference else None
		),
	)


def record_entry(entry_type, credits, monetary_value=0, direction=None, currency="USD", workspace=None, billing_event=None, reference=None, notes=None, source_key=None):
	if entry_type not in {"Opening Balance", "Purchase", "Allocation", "Reversal", "Adjustment"}:
		frappe.throw("Invalid credit stock entry type.", frappe.ValidationError)
	credits = cint(credits)
	if credits <= 0:
		frappe.throw("AI credits must be greater than zero.", frappe.ValidationError)
	direction = direction or ("Issue" if entry_type == "Allocation" else "Receipt")
	if direction not in {"Receipt", "Issue"}:
		frappe.throw("Invalid stock movement direction.", frappe.ValidationError)
	monetary_value = flt(monetary_value, 2)
	if monetary_value < 0:
		frappe.throw("Monetary value cannot be negative.", frappe.ValidationError)
	if source_key and frappe.db.exists(LEDGER, {"source_key": source_key}):
		return frappe.get_doc(LEDGER, frappe.db.get_value(LEDGER, {"source_key": source_key}, "name"))
	last = _last_entry(lock=True)
	prior_credits = cint(last.balance_credits) if last else 0
	prior_value = flt(last.balance_value, 8) if last else 0
	last_cost = flt(last.unit_cost, 10) if last else 0
	average_cost = prior_value / prior_credits if prior_credits > 0 else last_cost
	if direction == "Receipt":
		inventory_value = monetary_value
		unit_cost = inventory_value / credits if credits else 0
		balance_credits = prior_credits + credits
		balance_value = prior_value + inventory_value
		revenue = cogs = profit = 0
	else:
		unit_cost = average_cost
		cogs = flt(credits * unit_cost, 2)
		inventory_value = -cogs
		balance_credits = prior_credits - credits
		balance_value = flt(prior_value - cogs, 2)
		revenue = monetary_value
		profit = flt(revenue - cogs, 2)
	doc = frappe.get_doc({
		"doctype": LEDGER, "posting_datetime": now_datetime(), "entry_type": entry_type, "direction": direction,
		"credits": credits, "unit_cost": unit_cost, "inventory_value": inventory_value, "revenue": revenue,
		"cogs": cogs, "gross_profit": profit, "balance_credits": balance_credits, "balance_value": balance_value,
		"currency": currency or "USD", "workspace": workspace, "billing_event": billing_event, "source_key": source_key,
		"reference": reference, "notes": notes, "erpnext_status": "Pending" if direction == "Issue" and (revenue or cogs) else "Not Applicable",
	})
	doc.flags.credit_stock_service = True
	doc.insert(ignore_permissions=True)
	return doc


def protect_ledger_insert(doc, method=None):
	if not getattr(doc.flags, "credit_stock_service", False):
		frappe.throw("Credit stock entries must be created through Credit Management.", frappe.PermissionError)


def protect_ledger_update(doc, method=None):
	if not doc.is_new():
		frappe.throw("Credit stock ledger entries are permanent. Record a reversal or adjustment instead.", frappe.PermissionError)


def protect_ledger_delete(doc, method=None):
	frappe.throw("Credit stock ledger entries are permanent. Record a reversal or adjustment instead.", frappe.PermissionError)


def record_billing_allocation(billing_event):
	if not frappe.db.exists("VerityAI Billing Event", billing_event):
		frappe.throw("Billing event was not found.", frappe.DoesNotExistError)
	event = frappe.get_doc("VerityAI Billing Event", billing_event)
	if event.status != "Completed":
		frappe.throw("Only completed payments can allocate credit stock.", frappe.ValidationError)
	if event.transaction_kind == "Credit Top-Up":
		credits = cint(event.purchased_credits)
	else:
		credits = cint(frappe.db.get_value("VerityAI Plan", event.target_plan, "monthly_token_limit"))
		if event.billing_cycle == "Annual":
			credits *= 12
	if not credits:
		return None
	doc = record_entry("Allocation", credits, event.amount, "Issue", event.currency, event.workspace, event.name, event.gateway_reference or event.provider_reference, source_key=f"billing:{event.name}")
	settings = frappe.get_single(SETTINGS)
	if settings.enabled and settings.auto_post and doc.erpnext_status != "Posted":
		try:
			post_to_erpnext(doc.name)
		except Exception:
			frappe.log_error(title=f"ERPNext credit accounting post failed: {doc.name}", message=frappe.get_traceback())
	return doc


def configure_erpnext(values):
	values = values or {}
	doc = frappe.get_single(SETTINGS)
	doc.enabled = cint(values.get("enabled"))
	doc.auto_post = cint(values.get("auto_post"))
	url = str(values.get("url") or doc.erpnext_url or "").strip()
	if doc.enabled or url:
		doc.erpnext_url = _public_https_url(url)
	for fieldname in ("api_key", "api_secret"):
		value = str(values.get(fieldname) or "").strip()
		if value:
			setattr(doc, fieldname, value)
	if doc.enabled and (not _password_present(doc, "api_key") or not _password_present(doc, "api_secret")):
		frappe.throw("ERPNext API key and secret are required.", frappe.ValidationError)
	for fieldname in ("company", "currency", "receivable_account", "sales_account", "inventory_account", "cogs_account", "cost_center"):
		setattr(doc, fieldname, str(values.get(fieldname) or doc.get(fieldname) or "").strip() or None)
	doc.connection_status = "Not Checked" if doc.enabled else "Not Configured"
	doc.last_error = None
	doc.save(ignore_permissions=True)
	return summary(1)["erpnext"]


def _request(method, path, *, params=None, payload=None):
	doc = frappe.get_single(SETTINGS)
	base = _public_https_url(doc.erpnext_url)
	if not path.startswith("/api/"):
		frappe.throw("Invalid ERPNext API path.", frappe.ValidationError)
	response = requests.request(method, urljoin(base + "/", path.lstrip("/")), params=params, json=payload,
		headers={"Authorization": f"token {doc.get_password('api_key')}:{doc.get_password('api_secret')}", "Accept": "application/json", "Content-Type": "application/json"},
		timeout=TIMEOUT, allow_redirects=False)
	response.raise_for_status()
	return response.json()


def test_erpnext_connection():
	doc = frappe.get_single(SETTINGS)
	try:
		user = _request("GET", "/api/method/frappe.auth.get_logged_user").get("message")
		doc.db_set({"connection_status": "Connected", "last_checked_on": now_datetime(), "last_error": None}, update_modified=False)
		return {"connected": True, "user": user}
	except Exception as error:
		doc.db_set({"connection_status": "Failed", "last_checked_on": now_datetime(), "last_error": str(error)[:500]}, update_modified=False)
		raise


def _account_rows(settings, entry):
	rows = []
	if flt(entry.revenue):
		rows.extend([
			{"account": settings.receivable_account, "debit_in_account_currency": flt(entry.revenue, 2)},
			{"account": settings.sales_account, "credit_in_account_currency": flt(entry.revenue, 2), "cost_center": settings.cost_center},
		])
	if flt(entry.cogs):
		rows.extend([
			{"account": settings.cogs_account, "debit_in_account_currency": flt(entry.cogs, 2), "cost_center": settings.cost_center},
			{"account": settings.inventory_account, "credit_in_account_currency": flt(entry.cogs, 2)},
		])
	return rows


def post_to_erpnext(ledger_name):
	entry = frappe.get_doc(LEDGER, ledger_name)
	if entry.erpnext_status == "Posted":
		return {"posted": True, "journal_entry": entry.erpnext_journal_entry, "already_posted": True}
	settings = frappe.get_single(SETTINGS)
	if not settings.enabled:
		frappe.throw("Enable ERPNext accounting before posting.", frappe.ValidationError)
	required = ("company", "receivable_account", "sales_account", "inventory_account", "cogs_account", "cost_center")
	if any(not settings.get(fieldname) for fieldname in required):
		frappe.throw("Complete the ERPNext company and accounting mappings before posting.", frappe.ValidationError)
	accounts = _account_rows(settings, entry)
	if not accounts:
		frappe.throw("This ledger entry has no accounting value to post.", frappe.ValidationError)
	marker = f"VerityAI credit ledger {entry.name}"
	try:
		existing = _request("GET", "/api/resource/Journal Entry", params={"fields": '["name","docstatus"]', "filters": frappe.as_json([["user_remark", "=", marker]]), "limit_page_length": 1}).get("data") or []
		if existing:
			name = existing[0]["name"]
			docstatus = cint(existing[0].get("docstatus"))
			if docstatus == 2:
				frappe.throw(
					"The matching ERPNext Journal Entry is cancelled. Record a reversal or adjustment before reposting.",
					frappe.ValidationError,
				)
		else:
			created = _request("POST", "/api/resource/Journal Entry", payload={"voucher_type": "Journal Entry", "company": settings.company, "posting_date": nowdate(), "user_remark": marker, "accounts": accounts}).get("data") or {}
			name = created.get("name")
			if not name:
				frappe.throw("ERPNext did not return a Journal Entry identifier.", frappe.ValidationError)
			docstatus = cint(created.get("docstatus"))
		if docstatus != 1:
			_request("PUT", f"/api/resource/Journal Entry/{quote(name, safe='')}", payload={"docstatus": 1})
		entry.db_set({"erpnext_status": "Posted", "erpnext_journal_entry": name, "erpnext_error": None}, update_modified=False)
		return {"posted": True, "journal_entry": name, "already_posted": False}
	except Exception as error:
		entry.db_set({"erpnext_status": "Failed", "erpnext_error": str(error)[:500]}, update_modified=False)
		raise
