from unittest.mock import MagicMock, patch

import frappe
from frappe.tests.utils import FrappeTestCase

from verityai_saas import setup_doctypes
from verityai_saas.api._response import RateLimitExceeded, endpoint
from verityai_saas.api import admin as admin_api
from verityai_saas.api import assistant as assistant_api
from verityai_saas.api import integrations as integrations_api
from verityai_saas.services import engine, integrations, notifications, onboarding, paynow
from verityai_saas.services.admin_reauth import mark_admin_reauthenticated
from verityai_saas.tests.cleanup import cleanup_all_test_fixtures, cleanup_test_workspace


class TestSecureIntegrations(FrappeTestCase):
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
		settings = frappe.get_single("VerityAI Platform Settings")
		self.original_paynow = {
			"integration_id": settings.paynow_integration_id,
			"integration_key": settings.get_password("paynow_integration_key", raise_exception=False),
			"environment": settings.paynow_environment,
		}
		self.token = frappe.generate_hash(length=8).lower()
		self.owner = frappe.get_doc({
			"doctype": "User", "email": f"integration-owner-{self.token}@example.com",
			"first_name": "Integration", "last_name": "Owner", "user_type": "Website User", "send_welcome_email": 0,
		}).insert(ignore_permissions=True).name
		self.created = onboarding.create_workspace(self.owner, f"Integration Account {self.token}", f"Integration Workspace {self.token}")
		self.workspace = self.created["workspace"]
		self.tenant = self.created["engine_tenant"]
		self.plan = frappe.get_doc({
			"doctype": "VerityAI Plan", "plan_name": f"Integration Plan {self.token}", "plan_code": f"INT-{self.token.upper()}",
			"active": 1, "currency": "USD", "monthly_token_limit": 1000, "public_rate_limit_per_minute": 20,
			"can_use_email_notifications": 1, "can_use_custom_smtp": 1, "can_use_erpnext_integration": 1,
			"can_use_api_access": 1, "can_bring_own_ai_provider_key": 1, "can_remove_branding": 1,
		}).insert(ignore_permissions=True).name
		frappe.db.set_value("VerityAI Subscription", self.created["subscription"], {"plan": self.plan, "status": "Active"})
		frappe.db.set_value("VerityAI Workspace", self.workspace, "status", "Active")
		frappe.db.set_value("VerityAI Usage Wallet", self.created["wallet"], {"tokens_remaining": 1000, "status": "Normal"})

	def tearDown(self):
		super().tearDown()
		settings = frappe.get_single("VerityAI Platform Settings")
		settings.paynow_integration_id = self.original_paynow["integration_id"]
		settings.paynow_integration_key = self.original_paynow["integration_key"]
		settings.paynow_environment = self.original_paynow["environment"]
		settings.save(ignore_permissions=True)
		cleanup_test_workspace(self.workspace, users=[self.owner], engine_tenant=self.tenant, commit=False)
		if frappe.db.exists("VerityAI Plan", self.plan):
			frappe.delete_doc("VerityAI Plan", self.plan, ignore_permissions=True, force=True)
		frappe.db.commit()

	@patch("verityai_saas.services.integrations.socket.getaddrinfo", return_value=[(2, 1, 6, "", ("93.184.216.34", 443))])
	def test_provider_and_erpnext_secrets_are_write_only(self, _dns):
		provider = integrations.configure_provider(self.workspace, {"provider": "OpenAI-Compatible", "model": "safe-model", "base_url": "https://ai.example.com/v1", "api_key": "provider-secret"})
		self.assertTrue(provider["api_key_present"])
		self.assertNotIn("provider-secret", str(provider))
		erp = integrations.configure_erpnext(self.workspace, {"enabled": 1, "url": "https://erp.example.com", "api_key": "erp-key", "api_secret": "erp-secret"})
		self.assertTrue(erp["api_secret_present"])
		self.assertNotIn("erp-secret", str(integrations.integration_status(self.workspace)))
		config = engine.get_engine_configuration(self.workspace)
		self.assertEqual(config.get_password("provider_api_key"), "provider-secret")
		self.assertEqual(config.get_password("erpnext_api_secret"), "erp-secret")

	def test_paynow_credentials_are_encrypted_and_write_only(self):
		response = admin_api.configure_paynow({"integration_id": "test-integration", "integration_key": "paynow-secret", "environment": "Production"})
		self.assertTrue(response["success"])
		status = response["data"]
		self.assertTrue(status["configured"])
		self.assertTrue(status["checkout_enabled"])
		self.assertEqual(status["environment"], "Production")
		self.assertEqual(frappe.db.get_single_value("VerityAI Platform Settings", "paynow_environment"), "Production")
		frappe.clear_cache(doctype="VerityAI Platform Settings")
		self.assertEqual(paynow.operating_mode(), "Production")
		self.assertNotIn("paynow-secret", str(status))
		settings = frappe.get_single("VerityAI Platform Settings")
		self.assertEqual(settings.get_password("paynow_integration_key"), "paynow-secret")
		dashboard = admin_api.dashboard()["data"]
		self.assertEqual(dashboard["paynow"]["integration_id"], "test-integration")
		self.assertNotIn("paynow-secret", frappe.as_json(dashboard))
		test_status = admin_api.configure_paynow({"integration_id": "test-integration", "integration_key": "", "environment": "Test"})["data"]
		self.assertEqual(test_status["environment"], "Test")
		self.assertFalse(test_status["checkout_enabled"])
		frappe.clear_cache(doctype="VerityAI Platform Settings")
		self.assertEqual(paynow.operating_mode(), "Test")

	@patch("verityai_saas.services.paynow._environment_field_available", return_value=False)
	def test_missing_paynow_environment_field_fails_safely(self, _field_available):
		self.assertEqual(paynow.operating_mode(), "Test")
		with self.assertRaisesRegex(frappe.ValidationError, "database update"):
			paynow.configure({"integration_id": "test-integration", "integration_key": "secret", "environment": "Production"})

	def test_plan_gate_blocks_disabled_integrations(self):
		frappe.db.set_value("VerityAI Plan", self.plan, "can_use_api_access", 0)
		with self.assertRaises(frappe.PermissionError):
			integrations.create_api_credential(self.workspace, "Blocked", ["leads:read"])
		frappe.db.set_value("VerityAI Plan", self.plan, "can_bring_own_ai_provider_key", 0)
		with self.assertRaises(frappe.PermissionError):
			integrations.configure_provider(self.workspace, {"provider": "OpenAI", "model": "model", "api_key": "secret"})

	def test_api_tokens_are_hashed_scoped_and_revocable(self):
		created = integrations.create_api_credential(self.workspace, "Reporting", ["leads:read"])
		doc = frappe.get_doc("VerityAI API Credential", created["credential"])
		self.assertNotEqual(doc.token_hash, created["token"])
		self.assertNotIn(created["token"], str(integrations.integration_status(self.workspace)))
		with patch("frappe.get_request_header", side_effect=lambda name: created["token"] if name == "X-VerityAI-API-Key" else None):
			context = integrations.authenticate_api("leads:read")
			self.assertEqual(context.workspace.name, self.workspace)
			with self.assertRaises(frappe.PermissionError):
				integrations.authenticate_api("analytics:read")
		integrations.revoke_api_credential(self.workspace, created["credential"])
		with patch("frappe.get_request_header", side_effect=lambda name: created["token"] if name == "X-VerityAI-API-Key" else None):
			with self.assertRaises(frappe.AuthenticationError):
				integrations.authenticate_api("leads:read")

	@patch("verityai_saas.services.integrations.socket.getaddrinfo", return_value=[(2, 1, 6, "", ("93.184.216.34", 587))])
	def test_custom_smtp_is_encrypted_and_used_for_delivery(self, _dns):
		status = integrations.configure_smtp(self.workspace, {"enabled": 1, "host": "smtp.example.com", "port": 587, "use_tls": 1, "username": "mailer", "password": "smtp-secret", "sender_email": "sender@example.com"})
		self.assertTrue(status["password_present"])
		self.assertNotIn("smtp-secret", str(status))
		setting = frappe.get_doc("VerityAI Notification Setting", {"workspace": self.workspace})
		client = MagicMock()
		client.__enter__.return_value = client
		with patch("verityai_saas.services.integrations.socket.getaddrinfo", return_value=[(2, 1, 6, "", ("93.184.216.34", 587))]), patch("verityai_saas.services.notifications.smtplib.SMTP", return_value=client):
			notifications._deliver_email(self.workspace, setting, "customer@example.com", "Test", "<p>Safe</p>")
		client.starttls.assert_called_once()
		client.login.assert_called_once_with("mailer", "smtp-secret")
		client.send_message.assert_called_once()

	def test_api_rate_limit_keeps_http_429(self):
		@endpoint
		def limited():
			raise RateLimitExceeded("API rate limit exceeded.")
		result = limited()
		self.assertFalse(result["success"])
		self.assertEqual(result["code"], "RATE_LIMITED")
		self.assertEqual(frappe.local.response["http_status_code"], 429)
	def test_customer_cannot_view_or_change_integration_configuration(self):
		frappe.set_user(self.owner)
		responses = [
			integrations_api.get(self.workspace),
			integrations_api.update_provider(self.workspace, {}),
			integrations_api.update_erpnext(self.workspace, {}),
			integrations_api.update_smtp(self.workspace, {}),
			integrations_api.update_paynow(self.workspace, {}),
			integrations_api.create_credential(self.workspace, "Blocked", ["leads:read"]),
			integrations_api.revoke_credential(self.workspace, "missing"),
		]
		for response in responses:
			self.assertFalse(response["success"])
			self.assertEqual(response["code"], "WORKSPACE_FORBIDDEN")
		assistant = assistant_api.get(self.workspace)
		self.assertTrue(assistant["success"])
		self.assertNotIn("configuration", assistant["data"])
		frappe.set_user("Administrator")
		self.assertTrue(integrations_api.get(self.workspace)["success"])
	def test_plan_controls_widget_branding(self):
		engine.apply_plan_limits(self.workspace, self.plan)
		self.assertEqual(frappe.db.get_value("AI Tenant", self.tenant, "show_branding"), 0)
		frappe.db.set_value("VerityAI Plan", self.plan, "can_remove_branding", 0)
		engine.apply_plan_limits(self.workspace, self.plan)
		self.assertEqual(frappe.db.get_value("AI Tenant", self.tenant, "show_branding"), 1)
