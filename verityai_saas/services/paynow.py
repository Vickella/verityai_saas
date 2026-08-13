import hashlib
import hmac
import json
from collections.abc import Iterable
from decimal import Decimal, InvalidOperation
from urllib.parse import parse_qsl, urlencode, urlparse

import frappe
import requests
from frappe.utils import add_to_date, cint, flt, get_url, now_datetime

from verityai_saas.services import billing


INITIATE_URL = "https://www.paynow.co.zw/interface/initiatetransaction"
PAYNOW_HOSTS = {"paynow.co.zw", "www.paynow.co.zw", "staging.paynow.co.zw"}
PAID_STATUSES = {"paid", "awaiting delivery", "delivered"}
FINAL_FAILED_STATUSES = {"cancelled", "refunded"}
RISK_STATUSES = {"disputed"}
SETTINGS_DOCTYPE = "VerityAI Platform Settings"


def _settings_credentials():
	if not frappe.db.exists("DocType", SETTINGS_DOCTYPE):
		return "", ""
	settings = frappe.get_single(SETTINGS_DOCTYPE)
	try:
		integration_key = settings.get_password("paynow_integration_key", raise_exception=False) or ""
	except Exception:
		integration_key = ""
	return str(settings.paynow_integration_id or "").strip(), str(integration_key).strip()


def _configured_credentials():
	integration_id, integration_key = _settings_credentials()
	if integration_id and integration_key:
		return integration_id, integration_key
	return (
		str(frappe.conf.get("paynow_integration_id") or "").strip(),
		str(frappe.conf.get("paynow_integration_key") or "").strip(),
	)


def is_configured():
	return all(_configured_credentials())


def configuration_status():
	integration_id, integration_key = _settings_credentials()
	if integration_id and integration_key:
		return {"configured": True, "integration_id": integration_id, "source": "Encrypted platform settings"}
	configured_id = str(frappe.conf.get("paynow_integration_id") or "").strip()
	return {
		"configured": bool(configured_id and frappe.conf.get("paynow_integration_key")),
		"integration_id": configured_id,
		"source": "Site configuration" if configured_id else "Not configured",
	}


def configure(values):
	integration_id = str(values.get("integration_id") or "").strip()
	integration_key = str(values.get("integration_key") or "").strip()
	if not integration_id or len(integration_id) > 140:
		frappe.throw("A valid Paynow integration ID is required.", frappe.ValidationError)
	settings = frappe.get_single(SETTINGS_DOCTYPE)
	if not integration_key:
		_, existing_key = _settings_credentials()
		if not existing_key:
			frappe.throw("A Paynow integration key is required.", frappe.ValidationError)
	settings.paynow_integration_id = integration_id
	if integration_key:
		settings.paynow_integration_key = integration_key
	settings.save()
	return configuration_status()


def _credentials():
	integration_id, integration_key = _configured_credentials()
	if not integration_id or not integration_key:
		frappe.throw("Paynow is not configured for this site.", frappe.ValidationError)
	return integration_id, integration_key


def generate_hash(values: Iterable[str], integration_key: str):
	message = "".join(str(value or "") for value in values) + integration_key
	return hashlib.sha512(message.encode("utf-8")).hexdigest().upper()


def parse_message(raw_message):
	if isinstance(raw_message, bytes):
		raw_message = raw_message.decode("utf-8")
	pairs = parse_qsl(raw_message or "", keep_blank_values=True)
	return pairs, {key.lower(): value for key, value in pairs}


def verify_message(raw_message, integration_key):
	pairs, values = parse_message(raw_message)
	received_hash = values.get("hash", "")
	expected_hash = generate_hash(
		(value for key, value in pairs if key.lower() != "hash"), integration_key
	)
	if not received_hash or not hmac.compare_digest(received_hash.upper(), expected_hash):
		frappe.throw("Paynow response signature is invalid.", frappe.PermissionError)
	return values


def _safe_paynow_url(url, label):
	parsed = urlparse(url or "")
	if parsed.scheme != "https" or (parsed.hostname or "").lower() not in PAYNOW_HOSTS:
		frappe.throw(f"Paynow returned an invalid {label} URL.", frappe.ValidationError)
	if label == "checkout" and parsed.path.lower().rstrip("/") in {"", "/home", "/home/home"}:
		frappe.throw(
			"Paynow accepted the request but this merchant account is still in testing and cannot take payments. "
			"Ask Paynow to activate the integration before accepting customer orders.",
			frappe.ValidationError,
		)
	return url


def _public_urls(payment_reference, workspace):
	base_url = get_url().rstrip("/")
	return_query = urlencode({"workspace": workspace, "payment": payment_reference})
	result_query = urlencode({"payment": payment_reference})
	return (
		f"{base_url}/verityai/billing?{return_query}",
		f"{base_url}/api/method/verityai_saas.api.paynow.result?{result_query}",
	)


def _response_snapshot(values):
	return json.dumps({key: value for key, value in values.items() if key != "hash"}, sort_keys=True)


def _initiate_gateway_event(workspace_name, event_type, amount, additional_info, metadata=None):
	integration_id, integration_key = _credentials()
	payment = billing.create_billing_event(workspace_name, event_type, amount, "Pending", provider="Paynow")
	frappe.db.set_value("VerityAI Billing Event", payment, {"gateway_status": "Created", **(metadata or {})})
	return_url, result_url = _public_urls(payment, workspace_name)
	payload = {
		"id": integration_id, "reference": payment, "amount": f"{amount:.2f}", "additionalinfo": additional_info,
		"returnurl": return_url, "resulturl": result_url, "merchanttrace": payment[:32], "status": "Message",
	}
	payload["hash"] = generate_hash(payload.values(), integration_key)
	try:
		response = requests.post(INITIATE_URL, data=payload, timeout=20, allow_redirects=False)
		response.raise_for_status()
	except requests.RequestException:
		frappe.db.set_value("VerityAI Billing Event", payment, {"status": "Failed", "gateway_status": "Connection Error"})
		frappe.throw("Paynow could not be reached. Please try again.", frappe.ValidationError)
	_, unsigned_values = parse_message(response.text)
	if unsigned_values.get("status", "").lower() != "ok":
		frappe.db.set_value("VerityAI Billing Event", payment, {"status": "Failed", "gateway_status": "Error", "gateway_response_json": _response_snapshot(unsigned_values)})
		frappe.throw("Paynow could not start the transaction.", frappe.ValidationError)
	try:
		values = verify_message(response.text, integration_key)
	except frappe.PermissionError:
		frappe.db.set_value("VerityAI Billing Event", payment, {"status": "Failed", "gateway_status": "Invalid Signature"})
		raise
	checkout_url = _safe_paynow_url(values.get("browserurl"), "checkout")
	poll_url = _safe_paynow_url(values.get("pollurl"), "poll")
	frappe.db.set_value("VerityAI Billing Event", payment, {"checkout_url": checkout_url, "poll_url": poll_url, "gateway_status": values.get("status"), "gateway_response_json": _response_snapshot(values)})
	from verityai_saas.services.billing_documents import ensure_invoice_for_payment
	ensure_invoice_for_payment(payment)
	return {"payment": payment, "checkout_url": checkout_url, "status": "Pending"}


def initiate_checkout(workspace_name, plan_name, billing_cycle="Monthly", promotion_code=None):
	plan = frappe.get_doc("VerityAI Plan", plan_name)
	if not plan.active or plan.plan_code == "TRIAL":
		frappe.throw("Select an active paid plan.", frappe.ValidationError)
	if billing_cycle not in {"Monthly", "Annual"}:
		frappe.throw("Paynow checkout supports monthly or annual billing.", frappe.ValidationError)
	if (plan.currency or "USD").upper() != "USD":
		frappe.throw("This Paynow checkout currently supports USD plans only.", frappe.ValidationError)
	gross_amount = flt(plan.annual_price if billing_cycle == "Annual" else plan.monthly_price, 2)
	if gross_amount <= 0:
		frappe.throw("The selected plan does not have a valid checkout price.", frappe.ValidationError)
	from verityai_saas.services import commercial
	promotion = commercial.promotion_quote(workspace_name, plan.name, promotion_code, gross_amount)
	referral_discount_percent = commercial.referral_first_payment_discount(workspace_name, billing_cycle)
	if promotion.get("promotion") and referral_discount_percent:
		frappe.throw("Referral and promotion discounts cannot be combined.", frappe.ValidationError)
	discount_amount = promotion.get("discount_amount") or round(gross_amount * referral_discount_percent / 100, 2)
	amount = round(gross_amount - discount_amount, 2)
	if amount <= 0:
		frappe.throw("The checkout total must be greater than zero.", frappe.ValidationError)
	pending = frappe.get_all(
		"VerityAI Billing Event",
		filters={
			"workspace": workspace_name,
			"provider": "Paynow",
			"status": "Pending",
			"target_plan": plan.name,
			"billing_cycle": billing_cycle,
			"checkout_url": ["is", "set"],
			"creation": [">=", add_to_date(now_datetime(), minutes=-15)],
		},
		fields=["name", "checkout_url"],
		order_by="creation desc",
		limit=1,
	)
	if pending and not promotion_code and not referral_discount_percent:
		return {
			"payment": pending[0].name,
			"checkout_url": _safe_paynow_url(pending[0].checkout_url, "checkout"),
			"status": "Pending",
		}

	result = _initiate_gateway_event(workspace_name, "Payment", amount, f"VerityAI {plan.plan_name} plan", {
		"transaction_kind": "Subscription", "target_plan": plan.name, "billing_cycle": billing_cycle,
		"gross_amount": gross_amount, "discount_amount": discount_amount, "promotion": promotion.get("promotion"),
	})
	commercial.reserve_promotion(workspace_name, result["payment"], promotion)
	return result


def initiate_credit_checkout(workspace_name, credit_pack):
	subscription = frappe.db.get_value("VerityAI Subscription", {"workspace": workspace_name}, ["status"], as_dict=True, order_by="creation desc")
	if not subscription or subscription.status != "Active":
		frappe.throw("Choose a paid plan before purchasing additional AI credits.", frappe.PermissionError)
	pack = frappe.get_doc("VerityAI Credit Pack", credit_pack)
	if not pack.active or cint(pack.credits) <= 0 or flt(pack.price) <= 0 or (pack.currency or "USD") != "USD":
		frappe.throw("This AI credit pack is unavailable.", frappe.ValidationError)
	return _initiate_gateway_event(workspace_name, "Top-Up", flt(pack.price, 2), f"VerityAI {pack.pack_name}", {
		"transaction_kind": "Credit Top-Up", "credit_pack": pack.name, "purchased_credits": cint(pack.credits), "gross_amount": flt(pack.price, 2),
	})


def _decimal(value):
	try:
		return Decimal(str(value)).quantize(Decimal("0.01"))
	except (InvalidOperation, TypeError):
		frappe.throw("Paynow returned an invalid amount.", frappe.ValidationError)


def apply_status(payment_name, values):
	payment = frappe.get_doc("VerityAI Billing Event", payment_name)
	if payment.provider != "Paynow" or values.get("reference") != payment.name:
		frappe.throw("Paynow payment reference does not match.", frappe.PermissionError)
	if _decimal(values.get("amount")) != _decimal(payment.amount):
		frappe.throw("Paynow payment amount does not match.", frappe.PermissionError)
	status = (values.get("status") or "").strip()
	updates = {
		"gateway_status": status,
		"gateway_reference": values.get("paynowreference"),
		"gateway_response_json": _response_snapshot(values),
	}
	if values.get("pollurl"):
		updates["poll_url"] = _safe_paynow_url(values["pollurl"], "poll")
	status_key = status.lower()
	if status_key in PAID_STATUSES and payment.status not in {"Completed", "Cancelled"}:
		updates.update({"status": "Completed", "paid_on": frappe.utils.now_datetime()})
		frappe.db.set_value("VerityAI Billing Event", payment.name, updates)
		if payment.transaction_kind == "Credit Top-Up":
			billing.add_top_up(payment.workspace, payment.purchased_credits, payment.amount, values.get("paynowreference"), billing_event=payment.name)
		else:
			billing.assign_plan(payment.workspace, payment.target_plan, "Active", payment.billing_cycle)
			frappe.db.set_value("VerityAI Subscription", {"workspace": payment.workspace}, "last_payment_reference", values.get("paynowreference"))
			from verityai_saas.services.commercial import finalize_payment_rewards
			finalize_payment_rewards(payment.name)
		from verityai_saas.services.billing_documents import ensure_receipt_for_payment
		ensure_receipt_for_payment(payment.name)
		from verityai_saas.services.platform_email import send_payment_confirmation
		send_payment_confirmation(payment.workspace, payment.name)
	elif status_key in FINAL_FAILED_STATUSES:
		was_completed = payment.status == "Completed"
		if status_key == "refunded" and was_completed:
			refund = billing.initiate_refund(payment.workspace, payment.name, payment.amount, "Paynow reported a completed refund")
			billing.complete_refund(refund["refund"], values.get("paynowreference"))
		updates["status"] = "Cancelled"
		frappe.db.set_value("VerityAI Billing Event", payment.name, updates)
	elif status_key in RISK_STATUSES:
		updates["status"] = "Pending"
		frappe.db.set_value("VerityAI Billing Event", payment.name, updates)
		if payment.status == "Completed":
			billing.set_subscription_status(payment.workspace, "Past Due", "Paynow payment disputed")
	else:
		frappe.db.set_value("VerityAI Billing Event", payment.name, updates)
	return {"payment": payment.name, "status": updates.get("status", payment.status), "gateway_status": status, "transaction_kind": payment.transaction_kind or "Subscription"}


def poll_payment(payment_name):
	_, integration_key = _credentials()
	payment = frappe.get_doc("VerityAI Billing Event", payment_name)
	poll_url = _safe_paynow_url(payment.poll_url, "poll")
	try:
		response = requests.post(poll_url, data={}, timeout=20, allow_redirects=False)
		response.raise_for_status()
	except requests.RequestException:
		frappe.throw("Paynow payment status could not be confirmed.", frappe.ValidationError)
	values = verify_message(response.text, integration_key)
	return apply_status(payment.name, values)


def process_result(raw_message, expected_reference=None):
	_, integration_key = _credentials()
	values = verify_message(raw_message, integration_key)
	payment_name = values.get("reference")
	if expected_reference and payment_name != expected_reference:
		frappe.throw("Paynow payment reference does not match the callback URL.", frappe.PermissionError)
	if not payment_name or not frappe.db.exists("VerityAI Billing Event", payment_name):
		frappe.throw("Paynow payment was not found.", frappe.DoesNotExistError)
	# Paynow recommends independently polling important updates before fulfillment.
	return poll_payment(payment_name)
