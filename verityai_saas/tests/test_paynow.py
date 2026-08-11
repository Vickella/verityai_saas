from urllib.parse import urlencode
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from verityai_saas import setup_doctypes
from verityai_saas.api import billing as billing_api
from verityai_saas.services import billing, paynow
from verityai_saas.services.admin_reauth import mark_admin_reauthenticated
from verityai_saas.services.onboarding import create_workspace
from verityai_saas.tests.cleanup import cleanup_all_test_fixtures, cleanup_test_workspace


class FakeResponse:
	def __init__(self, text, status_code=200):
		self.text = text
		self.status_code = status_code

	def raise_for_status(self):
		if self.status_code >= 400:
			raise paynow.requests.HTTPError(f"HTTP {self.status_code}")


class TestPaynowBilling(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		frappe.set_user("Administrator")
		setup_doctypes.install()

	@classmethod
	def tearDownClass(cls):
		super().tearDownClass()
		cleanup_all_test_fixtures()

	def setUp(self):
		frappe.set_user("Administrator")
		mark_admin_reauthenticated()
		token = frappe.generate_hash(length=8).lower()
		self.owner = self.create_user(f"paynow-owner-{token}@example.com")
		created = create_workspace(
			self.owner,
			f"Paynow Account {token}",
			f"Paynow Workspace {token}",
		)
		self.workspace = created["workspace"]
		self.tenant = created["engine_tenant"]
		self.plan = frappe.get_doc({
			"doctype": "VerityAI Plan",
			"plan_name": f"Paynow Plan {token}",
			"plan_code": f"PAYNOW-{token.upper()}",
			"active": 1,
			"currency": "USD",
			"monthly_price": 25,
			"annual_price": 250,
			"monthly_token_limit": 250000,
			"max_tokens": 1200,
			"max_team_members": 5,
			"max_knowledge_sources": 20,
			"max_allowed_domains": 5,
		}).insert(ignore_permissions=True).name
		self.integration_key = "3e9fed89-60e1-4ce5-ab6e-6b1eb2d4f977"

	def tearDown(self):
		super().tearDown()
		cleanup_test_workspace(
			self.workspace,
			users=[self.owner],
			engine_tenant=self.tenant,
			commit=False,
		)
		frappe.db.delete("VerityAI Plan", {"name": self.plan})
		frappe.db.commit()

	def create_user(self, email):
		return frappe.get_doc({
			"doctype": "User",
			"email": email,
			"first_name": "Paynow",
			"last_name": "Tester",
			"user_type": "Website User",
			"send_welcome_email": 0,
		}).insert(ignore_permissions=True).name

	def signed_message(self, values):
		values = dict(values)
		values["hash"] = paynow.generate_hash(values.values(), self.integration_key)
		return urlencode(values)

	def create_payment(self, amount=25):
		name = billing.create_billing_event(
			self.workspace,
			"Payment",
			amount,
			"Pending",
			provider="Paynow",
		)
		frappe.db.set_value("VerityAI Billing Event", name, {
			"target_plan": self.plan,
			"billing_cycle": "Monthly",
			"poll_url": "https://www.paynow.co.zw/interface/checkpayment/test",
		})
		return name

	def test_hash_matches_paynow_documented_vector(self):
		values = [
			"1201",
			"TEST REF",
			"99.99",
			"A test ticket transaction",
			"http://www.google.com/search?q=returnurl",
			"http://www.google.com/search?q=resulturl",
			"Message",
		]
		self.assertEqual(
			paynow.generate_hash(values, self.integration_key),
			"2A033FC38798D913D42ECB786B9B19645ADEDBDE788862032F1BD82CF3B92DEF84F316385D5B40DBB35F1A4FD7D5BFE73835174136463CDD48C9366B0749C689",
		)

	def test_checkout_verifies_signature_before_returning_redirect(self):
		response_values = {
			"Status": "Ok",
			"BrowserUrl": "https://www.paynow.co.zw/Payment/ConfirmPayment/123",
			"PollUrl": "https://www.paynow.co.zw/Interface/CheckPayment/?guid=test",
		}
		response = FakeResponse(self.signed_message(response_values))
		with (
			patch.object(paynow, "_credentials", return_value=("1201", self.integration_key)),
			patch.object(paynow, "get_url", return_value="https://app.example.com"),
			patch.object(paynow.requests, "post", return_value=response) as post,
		):
			result = paynow.initiate_checkout(self.workspace, self.plan)
			repeated = paynow.initiate_checkout(self.workspace, self.plan)

		self.assertEqual(post.call_count, 1)
		self.assertEqual(repeated["payment"], result["payment"])
		payload = post.call_args.kwargs["data"]
		self.assertEqual(
			payload["hash"],
			paynow.generate_hash(
				(value for key, value in payload.items() if key != "hash"),
				self.integration_key,
			),
		)
		self.assertEqual(result["checkout_url"], response_values["BrowserUrl"])
		payment = frappe.get_doc("VerityAI Billing Event", result["payment"])
		self.assertEqual(payment.target_plan, self.plan)
		self.assertEqual(payment.provider, "Paynow")
		self.assertEqual(payment.poll_url, response_values["PollUrl"])

	def test_customer_credit_pack_checkout_records_fulfilment_metadata(self):
		billing.assign_plan(self.workspace, self.plan, "Active", "Monthly")
		pack = frappe.db.get_value("VerityAI Credit Pack", {"pack_code": "CREDITS-1M"}, "name")
		response_values = {
			"Status": "Ok", "BrowserUrl": "https://www.paynow.co.zw/Payment/ConfirmPayment/topup",
			"PollUrl": "https://www.paynow.co.zw/Interface/CheckPayment/?guid=topup",
		}
		with (
			patch.object(paynow, "_credentials", return_value=("1201", self.integration_key)),
			patch.object(paynow, "get_url", return_value="https://app.example.com"),
			patch.object(paynow.requests, "post", return_value=FakeResponse(self.signed_message(response_values))),
		):
			result = paynow.initiate_credit_checkout(self.workspace, pack)
		event = frappe.get_doc("VerityAI Billing Event", result["payment"])
		self.assertEqual(event.transaction_kind, "Credit Top-Up")
		self.assertEqual(event.purchased_credits, 1_000_000)
		self.assertEqual(float(event.amount), 10)

	def test_promotion_discount_is_reserved_against_the_payment(self):
		promotion = frappe.get_doc({
			"doctype": "VerityAI Promotion", "promotion_name": f"Launch {self.workspace}",
			"code": f"SAVE-{frappe.generate_hash(length=6).upper()}", "active": 1,
			"discount_percent": 20, "bonus_credits": 100_000, "per_account_limit": 1,
		}).insert(ignore_permissions=True)
		response_values = {
			"Status": "Ok", "BrowserUrl": "https://www.paynow.co.zw/Payment/ConfirmPayment/promo",
			"PollUrl": "https://www.paynow.co.zw/Interface/CheckPayment/?guid=promo",
		}
		try:
			with (
				patch.object(paynow, "_credentials", return_value=("1201", self.integration_key)),
				patch.object(paynow, "get_url", return_value="https://app.example.com"),
				patch.object(paynow.requests, "post", return_value=FakeResponse(self.signed_message(response_values))),
			):
				result = paynow.initiate_checkout(self.workspace, self.plan, promotion_code=promotion.code)
			event = frappe.get_doc("VerityAI Billing Event", result["payment"])
			self.assertEqual(float(event.amount), 20)
			self.assertEqual(float(event.discount_amount), 5)
			self.assertTrue(frappe.db.exists("VerityAI Promotion Redemption", {"billing_event": event.name, "status": "Reserved"}))
		finally:
			frappe.db.delete("VerityAI Promotion Redemption", {"promotion": promotion.name})
			frappe.delete_doc("VerityAI Promotion", promotion.name, ignore_permissions=True, force=True)

	def test_invalid_initiation_signature_never_returns_checkout_url(self):
		response = FakeResponse(
			urlencode({
				"Status": "Ok",
				"BrowserUrl": "https://www.paynow.co.zw/Payment/ConfirmPayment/123",
				"PollUrl": "https://www.paynow.co.zw/Interface/CheckPayment/?guid=test",
				"Hash": "BAD",
			})
		)
		with (
			patch.object(paynow, "_credentials", return_value=("1201", self.integration_key)),
			patch.object(paynow, "get_url", return_value="https://app.example.com"),
			patch.object(paynow.requests, "post", return_value=response),
			self.assertRaises(frappe.PermissionError),
		):
			paynow.initiate_checkout(self.workspace, self.plan)
		self.assertEqual(
			frappe.db.get_value(
				"VerityAI Billing Event",
				{"workspace": self.workspace, "provider": "Paynow"},
				"status",
			),
			"Failed",
		)

	def test_callback_is_polled_then_activates_plan_idempotently(self):
		payment = self.create_payment()
		values = {
			"reference": payment,
			"paynowreference": "PN-123",
			"amount": "25.00",
			"status": "Paid",
			"pollurl": "https://www.paynow.co.zw/interface/checkpayment/test",
		}
		message = self.signed_message(values)
		with (
			patch.object(paynow, "_credentials", return_value=("1201", self.integration_key)),
			patch.object(paynow.requests, "post", return_value=FakeResponse(message)) as post,
		):
			first = paynow.process_result(message)
			second = paynow.process_result(message)

		self.assertEqual(first["status"], "Completed")
		self.assertEqual(second["status"], "Completed")
		self.assertEqual(post.call_count, 2)
		self.assertEqual(frappe.db.get_value("VerityAI Billing Event", payment, "status"), "Completed")
		self.assertEqual(
			frappe.db.get_value("VerityAI Subscription", {"workspace": self.workspace}, "plan"),
			self.plan,
		)
		self.assertEqual(frappe.db.get_value("AI Tenant", self.tenant, "active"), 1)
		self.assertEqual(
			frappe.db.get_value("VerityAI Usage Wallet", {"workspace": self.workspace}, "opening_token_allowance"),
			250000,
		)

	def test_refund_suspends_an_already_activated_subscription(self):
		payment = self.create_payment()
		paid = {
			"reference": payment,
			"paynowreference": "PN-REFUND-1",
			"amount": "25.00",
			"status": "Paid",
			"pollurl": "https://www.paynow.co.zw/interface/checkpayment/test",
		}
		paynow.apply_status(payment, paid)
		refunded = {**paid, "status": "Refunded"}
		result = paynow.apply_status(payment, refunded)

		self.assertEqual(result["status"], "Cancelled")
		self.assertEqual(frappe.db.get_value("VerityAI Workspace", self.workspace, "status"), "Suspended")
		self.assertEqual(frappe.db.get_value("AI Tenant", self.tenant, "active"), 0)
		self.assertEqual(
			frappe.db.get_value("VerityAI Subscription", {"workspace": self.workspace}, "status"),
			"Suspended",
		)

	def test_annual_billing_keeps_monthly_wallet_period_and_rolls_forward(self):
		billing.assign_plan(self.workspace, self.plan, "Active", "Annual")
		wallet_name = frappe.db.get_value("VerityAI Usage Wallet", {"workspace": self.workspace}, "name")
		wallet = frappe.get_doc("VerityAI Usage Wallet", wallet_name)
		self.assertLessEqual((frappe.utils.getdate(wallet.period_end) - frappe.utils.getdate(wallet.period_start)).days, 31)
		frappe.db.set_value("VerityAI Usage Wallet", wallet_name, {
			"period_start": "2026-06-01",
			"period_end": "2026-06-30",
			"top_up_tokens": 5000,
			"tokens_used": 250000,
			"tokens_remaining": 5000,
			"status": "Warning",
		})
		billing.roll_usage_periods()
		wallet.reload()
		self.assertGreaterEqual(frappe.utils.getdate(wallet.period_end), frappe.utils.getdate(frappe.utils.today()))
		self.assertEqual(wallet.top_up_tokens, 5000)
		self.assertEqual(wallet.tokens_used, 0)
		self.assertEqual(wallet.tokens_remaining, 255000)
		self.assertEqual(wallet.status, "Normal")

	def test_plan_renewal_never_restores_consumed_purchased_credits(self):
		billing.assign_plan(self.workspace, self.plan, "Active", "Monthly")
		billing.add_top_up(self.workspace, 5000)
		wallet_name = frappe.db.get_value("VerityAI Usage Wallet", {"workspace": self.workspace}, "name")
		frappe.db.set_value("VerityAI Usage Wallet", wallet_name, {"tokens_used": 252000, "tokens_remaining": 3000})
		billing.assign_plan(self.workspace, self.plan, "Active", "Monthly")
		wallet = frappe.db.get_value("VerityAI Usage Wallet", wallet_name, ["top_up_tokens", "tokens_used", "tokens_remaining"], as_dict=True)
		self.assertEqual(wallet.top_up_tokens, 3000)
		self.assertEqual(wallet.tokens_used, 0)
		self.assertEqual(wallet.tokens_remaining, 253000)

	def test_credit_top_up_is_fulfilled_once_and_refund_does_not_suspend_plan(self):
		billing.assign_plan(self.workspace, self.plan, "Active", "Monthly")
		payment = billing.create_billing_event(self.workspace, "Top-Up", 10, "Pending", provider="Paynow")
		frappe.db.set_value("VerityAI Billing Event", payment, {
			"transaction_kind": "Credit Top-Up", "purchased_credits": 1_000_000,
		})
		paid = {"reference": payment, "paynowreference": "PN-TOPUP", "amount": "10.00", "status": "Paid"}
		paynow.apply_status(payment, paid)
		paynow.apply_status(payment, paid)
		wallet = frappe.db.get_value("VerityAI Usage Wallet", {"workspace": self.workspace}, ["top_up_tokens", "tokens_remaining"], as_dict=True)
		self.assertEqual(wallet.top_up_tokens, 1_000_000)
		self.assertEqual(wallet.tokens_remaining, 1_250_000)
		paynow.apply_status(payment, {**paid, "status": "Refunded"})
		self.assertEqual(frappe.db.get_value("VerityAI Subscription", {"workspace": self.workspace}, "status"), "Active")
		self.assertEqual(frappe.db.get_value("VerityAI Usage Wallet", {"workspace": self.workspace}, "top_up_tokens"), 0)

	def test_tampered_callback_and_customer_manual_event_are_rejected(self):
		payment = self.create_payment()
		message = urlencode({
			"reference": payment,
			"paynowreference": "PN-123",
			"amount": "1.00",
			"status": "Paid",
			"pollurl": "https://www.paynow.co.zw/interface/checkpayment/test",
			"hash": "BAD",
		})
		with (
			patch.object(paynow, "_credentials", return_value=("1201", self.integration_key)),
			patch.object(paynow.requests, "post") as post,
			self.assertRaises(frappe.PermissionError),
		):
			paynow.process_result(message)
		post.assert_not_called()

		frappe.set_user(self.owner)
		response = billing_api.manual_event(self.workspace, "Payment", 25, "Completed")
		self.assertFalse(response["success"])
		self.assertEqual(response["code"], "WORKSPACE_FORBIDDEN")

	def test_operator_top_up_updates_wallet_and_immutable_ledger(self):
		before = frappe.db.get_value(
			"VerityAI Usage Wallet", {"workspace": self.workspace}, "tokens_remaining"
		)
		result = billing.add_top_up(self.workspace, 5000, 5, "TOPUP-1")
		wallet = frappe.get_doc("VerityAI Usage Wallet", result["wallet"])
		self.assertEqual(wallet.top_up_tokens, 5000)
		self.assertEqual(wallet.tokens_remaining, before + 5000)
		self.assertTrue(frappe.db.exists("VerityAI Usage Transaction", {
			"name": result["transaction"],
			"transaction_type": "Top-Up",
			"total_tokens": 5000,
		}))
		self.assertEqual(frappe.db.get_value("VerityAI Billing Event", result["event"], "status"), "Completed")
