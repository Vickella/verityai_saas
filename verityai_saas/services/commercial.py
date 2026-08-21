import re

import frappe
from frappe.utils import add_days, cint, flt, getdate, now_datetime, today


REFERRAL_REWARD_CREDITS = 50_000
REFERRAL_DISCOUNT_PERCENT = 25
REFERRAL_REVIEW_DAYS = 14
PROMOTIONAL_CREDIT_DAYS = 90
MAX_MONTHLY_REFERRAL_REWARDS = 5


def normalize_code(value):
	code = re.sub(r"[^A-Z0-9_-]", "", str(value or "").strip().upper())[:40]
	return code


def ensure_account_referral_code(account_name):
	code = frappe.db.get_value("VerityAI Account", account_name, "referral_code")
	if code:
		return code
	for _ in range(10):
		code = f"VAI-{frappe.generate_hash(length=8).upper()}"
		if not frappe.db.exists("VerityAI Account", {"referral_code": code}):
			frappe.db.set_value("VerityAI Account", account_name, "referral_code", code)
			return code
	frappe.throw("Could not generate a unique referral code. Please try again.", frappe.ValidationError)


def resolve_referrer(referral_code, owner_user=None):
	code = normalize_code(referral_code)
	if not code:
		return None
	referrer = frappe.db.get_value("VerityAI Account", {"referral_code": code}, ["name", "owner_user"], as_dict=True)
	if not referrer:
		frappe.throw("The referral code is invalid.", frappe.ValidationError)
	if owner_user and referrer.owner_user == owner_user:
		frappe.throw("You cannot use your own referral code.", frappe.ValidationError)
	return referrer.name


def promotion_quote(workspace_name, plan_name, code, gross_amount):
	code = normalize_code(code)
	if not code:
		return {"promotion": None, "discount_amount": 0, "bonus_credits": 0}
	promotion = frappe.db.get_value("VerityAI Promotion", {"code": code}, "name")
	if not promotion:
		frappe.throw("The promotion code is invalid.", frappe.ValidationError)
	doc = frappe.get_doc("VerityAI Promotion", promotion)
	now = getdate(today())
	if not doc.active or (doc.valid_from and getdate(doc.valid_from) > now) or (doc.valid_until and getdate(doc.valid_until) < now):
		frappe.throw("This promotion is not active.", frappe.ValidationError)
	if doc.minimum_plan and doc.minimum_plan != plan_name:
		frappe.throw("This promotion does not apply to the selected plan.", frappe.ValidationError)
	workspace = frappe.get_doc("VerityAI Workspace", workspace_name)
	granted = {"status": ["in", ["Reserved", "Granted"]]}
	if cint(doc.max_redemptions) and frappe.db.count("VerityAI Promotion Redemption", {"promotion": doc.name, **granted}) >= cint(doc.max_redemptions):
		frappe.throw("This promotion has reached its redemption limit.", frappe.ValidationError)
	if cint(doc.per_account_limit) and frappe.db.count("VerityAI Promotion Redemption", {"promotion": doc.name, "account": workspace.account, **granted}) >= cint(doc.per_account_limit):
		frappe.throw("This promotion has already been used by this account.", frappe.ValidationError)
	discount = min(round(flt(gross_amount) * flt(doc.discount_percent) / 100, 2), flt(gross_amount))
	return {"promotion": doc.name, "discount_amount": discount, "bonus_credits": cint(doc.bonus_credits)}


def referral_first_payment_discount(workspace_name, billing_cycle):
	if billing_cycle != "Monthly":
		return 0
	account = frappe.db.get_value("VerityAI Workspace", workspace_name, "account")
	if not account or not frappe.db.get_value("VerityAI Account", account, "referred_by"):
		return 0
	workspace_names = frappe.get_all("VerityAI Workspace", filters={"account": account}, pluck="name")
	if frappe.db.exists("VerityAI Billing Event", {"workspace": ["in", workspace_names], "event_type": "Payment", "status": "Completed"}):
		return 0
	return REFERRAL_DISCOUNT_PERCENT


def reserve_promotion(workspace_name, payment_name, quote):
	if not quote.get("promotion"):
		return None
	workspace = frappe.get_doc("VerityAI Workspace", workspace_name)
	return frappe.get_doc({
		"doctype": "VerityAI Promotion Redemption", "promotion": quote["promotion"], "account": workspace.account,
		"workspace": workspace_name, "billing_event": payment_name, "status": "Reserved",
		"discount_amount": quote.get("discount_amount") or 0, "bonus_credits": quote.get("bonus_credits") or 0,
	}).insert(ignore_permissions=True).name


def finalize_payment_rewards(payment_name):
	payment = frappe.get_doc("VerityAI Billing Event", payment_name)
	redemption = frappe.db.get_value("VerityAI Promotion Redemption", {"billing_event": payment.name, "status": "Reserved"}, "name")
	if redemption:
		doc = frappe.get_doc("VerityAI Promotion Redemption", redemption)
		doc.status = "Granted"
		doc.redeemed_on = now_datetime()
		doc.save(ignore_permissions=True)
		if cint(doc.bonus_credits):
			from verityai_saas.services.billing import add_promotional_credits
			add_promotional_credits(payment.workspace, doc.bonus_credits, add_days(today(), PROMOTIONAL_CREDIT_DAYS), doc.name)
	_create_referral_reward(payment)


def _create_referral_reward(payment):
	workspace = frappe.get_doc("VerityAI Workspace", payment.workspace)
	referred_account = frappe.get_doc("VerityAI Account", workspace.account)
	referrer_account = referred_account.referred_by
	if not referrer_account or frappe.db.exists("VerityAI Referral Reward", {"referred_account": referred_account.name}):
		return None
	referrer = frappe.get_doc("VerityAI Account", referrer_account)
	if referrer.owner_user == referred_account.owner_user or (referrer.billing_email and referrer.billing_email == referred_account.billing_email):
		return None
	month_start = frappe.utils.get_first_day(today())
	if frappe.db.count("VerityAI Referral Reward", {"referrer_account": referrer.name, "creation": [">=", month_start], "status": ["in", ["Pending", "Granted"]]}) >= MAX_MONTHLY_REFERRAL_REWARDS:
		return None
	referrer_workspace = frappe.db.get_value("VerityAI Workspace", {"account": referrer.name, "status": ["in", ["Trial", "Active"]]}, "name", order_by="creation asc")
	if not referrer_workspace:
		return None
	return frappe.get_doc({
		"doctype": "VerityAI Referral Reward", "referrer_account": referrer.name, "referrer_workspace": referrer_workspace,
		"referred_account": referred_account.name, "referred_workspace": workspace.name, "billing_event": payment.name,
		"reward_credits": REFERRAL_REWARD_CREDITS, "status": "Pending", "eligible_on": add_days(today(), REFERRAL_REVIEW_DAYS),
		"expires_on": add_days(today(), REFERRAL_REVIEW_DAYS + PROMOTIONAL_CREDIT_DAYS),
	}).insert(ignore_permissions=True).name


def process_referral_rewards():
	for row in frappe.get_all("VerityAI Referral Reward", filters={"status": "Pending", "eligible_on": ["<=", today()]}, fields=["name", "billing_event", "referrer_workspace", "reward_credits", "expires_on"]):
		if not frappe.db.exists("VerityAI Billing Event", {"name": row.billing_event, "status": "Completed"}):
			frappe.db.set_value("VerityAI Referral Reward", row.name, {"status": "Rejected", "review_note": "Qualifying payment is no longer completed."})
			continue
		if frappe.db.exists("VerityAI Billing Event", {"event_type": "Refund", "gateway_reference": row.billing_event, "status": ["in", ["Pending", "Completed"]]}):
			frappe.db.set_value("VerityAI Referral Reward", row.name, {"status": "Rejected", "review_note": "Qualifying payment was refunded."})
			continue
		from verityai_saas.services.billing import add_promotional_credits
		add_promotional_credits(row.referrer_workspace, row.reward_credits, row.expires_on, row.name)
		frappe.db.set_value("VerityAI Referral Reward", row.name, {"status": "Granted", "granted_on": now_datetime()})
	frappe.db.commit()


def reverse_payment_rewards(payment_name):
	redemption = frappe.db.get_value("VerityAI Promotion Redemption", {"billing_event": payment_name, "status": ["in", ["Reserved", "Granted"]]}, "name")
	if redemption:
		redemption_doc = frappe.get_doc("VerityAI Promotion Redemption", redemption)
		if redemption_doc.status == "Granted" and cint(redemption_doc.bonus_credits):
			_remove_promotional_credits(redemption_doc.workspace, redemption_doc.bonus_credits)
		frappe.db.set_value("VerityAI Promotion Redemption", redemption, "status", "Reversed")
	reward = frappe.db.get_value("VerityAI Referral Reward", {"billing_event": payment_name, "status": ["in", ["Pending", "Granted"]]}, ["name", "status", "referrer_workspace", "reward_credits"], as_dict=True)
	if not reward:
		return
	if reward.status == "Granted":
		_remove_promotional_credits(reward.referrer_workspace, reward.reward_credits)
	frappe.db.set_value("VerityAI Referral Reward", reward.name, {"status": "Reversed", "review_note": "Qualifying payment was refunded."})


def _remove_promotional_credits(workspace_name, credits):
	wallet_name = frappe.db.get_value("VerityAI Usage Wallet", {"workspace": workspace_name}, "name")
	if not wallet_name:
		return 0
	wallet = frappe.get_doc("VerityAI Usage Wallet", wallet_name)
	reversal = min(cint(wallet.promotional_credits), cint(wallet.tokens_remaining), cint(credits))
	wallet.promotional_credits = max(cint(wallet.promotional_credits) - reversal, 0)
	wallet.tokens_remaining = max(cint(wallet.tokens_remaining) - reversal, 0)
	if not wallet.promotional_credits:
		wallet.promotional_credits_expire_on = None
	wallet.save(ignore_permissions=True)
	workspace = frappe.get_doc("VerityAI Workspace", workspace_name)
	from verityai_saas.services.billing import _sync_engine_credit_limit
	_sync_engine_credit_limit(workspace, wallet)
	return reversal
