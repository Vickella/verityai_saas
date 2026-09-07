from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from verityai_saas.api import audits as audit_api
from verityai_saas.growth import audits
from verityai_saas.growth.checks import deterministic_checks, score_findings
from verityai_saas.growth.url_security import FetchResult, canonical_public_url, fetch_public_html, resolve_public_addresses
from verityai_saas.services import growth
from verityai_saas.services.onboarding import create_workspace
from verityai_saas.setup_doctypes import ensure_doctypes
from verityai_saas.tests.cleanup import cleanup_test_workspace


PUBLIC_DNS = [(2, 1, 6, "", ("93.184.216.34", 443))]
PRIVATE_DNS = [(2, 1, 6, "", ("127.0.0.1", 80))]


class FakeResponse:
	def __init__(self, status=200, headers=None, body=b""):
		self.status = status
		self._headers = list((headers or {}).items())
		self.body = body

	def getheaders(self):
		return self._headers

	def read(self, size=-1):
		return self.body if size < 0 else self.body[:size]


class FakeConnection:
	def close(self):
		return None


class TestWebsiteAuditSecurity(FrappeTestCase):
	def test_url_is_canonical_and_drops_query_secrets(self):
		self.assertEqual(canonical_public_url("Example.COM/path?token=secret#section"), "https://example.com/path")
		with self.assertRaises(frappe.PermissionError):
			canonical_public_url("http://localhost/admin")
		with self.assertRaises(frappe.PermissionError):
			canonical_public_url("http://127.0.0.1/admin")
		with self.assertRaises(frappe.ValidationError):
			canonical_public_url("https://user:password@example.com")
		with self.assertRaises(frappe.ValidationError):
			canonical_public_url("https://127.0.0.1\\example.com/")
		with self.assertRaises(frappe.ValidationError):
			canonical_public_url("https://example.com:8443")

	def test_resolution_rejects_any_private_or_mixed_address(self):
		with self.assertRaises(frappe.PermissionError):
			resolve_public_addresses("localhost", 80, resolver=lambda *args, **kwargs: PRIVATE_DNS)
		mixed = PUBLIC_DNS + PRIVATE_DNS
		with self.assertRaises(frappe.PermissionError):
			resolve_public_addresses("example.com", 443, resolver=lambda *args, **kwargs: mixed)

	def test_redirect_is_re_resolved_and_rebinding_target_is_blocked(self):
		calls = []

		def resolver(host, port, **kwargs):
			return PUBLIC_DNS if host == "example.com" else PRIVATE_DNS

		def opener(url, address, timeout):
			calls.append((url, address))
			return FakeConnection(), FakeResponse(302, {"Location": "http://rebound.test-target/secret"})

		with self.assertRaises(frappe.PermissionError):
			fetch_public_html("https://example.com", resolver=resolver, opener=opener)
		self.assertEqual(calls, [("https://example.com/", "93.184.216.34")])

	def test_fetch_is_ip_pinned_and_size_bounded(self):
		seen = []

		def opener(url, address, timeout):
			seen.append(address)
			return FakeConnection(), FakeResponse(200, {"Content-Type": "text/html"}, b"<html><title>Safe page</title></html>")

		result = fetch_public_html("https://example.com", resolver=lambda *args, **kwargs: PUBLIC_DNS, opener=opener)
		self.assertEqual(result.resolved_ip, "93.184.216.34")
		self.assertEqual(seen, ["93.184.216.34"])
		with self.assertRaises(frappe.ValidationError):
			fetch_public_html(
				"https://example.com", resolver=lambda *args, **kwargs: PUBLIC_DNS,
				opener=lambda *args: (FakeConnection(), FakeResponse(200, {"Content-Type": "text/html"}, b"12345")),
				maximum_bytes=4,
			)

	def test_fetch_rejects_unsafe_response_and_redirect_policies(self):
		resolver = lambda *args, **kwargs: PUBLIC_DNS

		def fetch_with(response):
			return fetch_public_html(
				"https://example.com", resolver=resolver,
				opener=lambda *args: (FakeConnection(), response),
			)

		with self.assertRaises(frappe.ValidationError):
			fetch_with(FakeResponse(200, {"Content-Type": "application/json"}, b"{}"))
		with self.assertRaises(frappe.ValidationError):
			fetch_with(FakeResponse(200, {"Content-Type": "text/html", "Content-Encoding": "gzip"}, b"data"))
		with self.assertRaises(frappe.PermissionError):
			fetch_with(FakeResponse(302, {"Location": "http://example.com/insecure"}))
		with self.assertRaises(frappe.ValidationError):
			fetch_with(FakeResponse(302, {"Location": "https://example.com/"}))

	def test_deterministic_findings_only_claim_measured_evidence(self):
		html = b"""<html lang="en"><head><title>Reliable Business Website</title>
		<meta name="description" content="A clear and useful description for a reliable business website that serves customers.">
		<meta name="viewport" content="width=device-width"><link rel="canonical" href="https://example.com/"></head>
		<body><h1>Reliable service</h1><p>Useful facts for customers.</p><button>Contact us</button><img alt="Team" src="team.jpg"></body></html>"""
		result = FetchResult(
			url="https://example.com/", status_code=200,
			headers={
				"content-type": "text/html",
				"content-security-policy": "default-src 'self'",
				"strict-transport-security": "max-age=100",
				"x-content-type-options": "nosniff",
				"referrer-policy": "strict-origin",
			},
			body=html, resolved_ip="93.184.216.34", duration_ms=20, redirect_count=0,
		)
		findings = deterministic_checks(result)
		codes = {row["check_code"] for row in findings}
		self.assertTrue({"page_title", "meta_description", "viewport", "security_headers", "single_h1"}.issubset(codes))
		self.assertTrue(all(isinstance(row["measured"], dict) for row in findings))
		overall, category_scores = score_findings(findings)
		self.assertGreaterEqual(overall, 0)
		self.assertLessEqual(overall, 100)
		self.assertIn("Metadata", category_scores)


class TestWebsiteAuditLifecycle(FrappeTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		ensure_doctypes()
		growth.seed_default_channels()
		self.original_flags = growth.feature_flags()
		self.original_doctor_configuration = growth.website_doctor_configuration()
		self.token = frappe.generate_hash(length=8).lower()
		self.owner = f"audit-owner-{self.token}@example.com"
		frappe.get_doc({
			"doctype": "User", "email": self.owner, "first_name": "Audit", "last_name": "Owner",
			"user_type": "Website User", "send_welcome_email": 0,
		}).insert(ignore_permissions=True)
		self.created = create_workspace(self.owner, f"Audit Account {self.token}", f"Audit Workspace {self.token}")
		self.audit_names = []

	def _complete_public_audit(self):
		growth.configure_feature_flags({"public_audits_enabled": 1})
		with patch("frappe.enqueue"):
			created = audits.request_public_audit("https://example.com")
		self.audit_names.append(created["audit"])
		fetch = FetchResult(
			url="https://example.com/", status_code=200, headers={"content-type": "text/html"},
			body=b"<html lang='en'><head><title>Example Business</title></head><body><h1>Welcome</h1></body></html>",
			resolved_ip="93.184.216.34", duration_ms=20, redirect_count=0,
		)
		with patch("verityai_saas.growth.audits.fetch_public_html", return_value=fetch), patch(
			"verityai_saas.growth.audits.run_pagespeed", return_value=([], 0, 0)
		):
			audits.process_audit(created["audit"])
		return created

	def tearDown(self):
		frappe.set_user("Administrator")
		growth.configure_website_doctor({"crm_workspace": self.original_doctor_configuration.get("crm_workspace")})
		frappe.db.delete("VerityAI Consent Record", {"source": "Public Website Doctor"})
		frappe.db.delete("VerityAI Suppression Record", {"source": "Public Website Doctor"})
		for audit_name in self.audit_names:
			frappe.db.delete("VerityAI Website Audit Evidence", {"audit": audit_name})
			frappe.db.delete("VerityAI Growth Event", {"object_type": "VerityAI Website Audit", "object_name": audit_name})
			frappe.db.delete("VerityAI Website Audit", {"name": audit_name})
		cleanup_test_workspace(self.created["workspace"], users=[self.owner], engine_tenant=self.created["engine_tenant"], commit=False)
		growth.configure_feature_flags(self.original_flags)
		frappe.db.commit()

	def test_public_release_flag_and_opaque_token_are_enforced(self):
		growth.configure_feature_flags({"public_audits_enabled": 0})
		with self.assertRaises(frappe.PermissionError):
			audits.request_public_audit("https://example.com")
		growth.configure_feature_flags({"public_audits_enabled": 1})
		with patch("frappe.enqueue"):
			created = audits.request_public_audit("https://example.com?secret=removed")
		self.audit_names.append(created["audit"])
		doc = frappe.get_doc("VerityAI Website Audit", created["audit"])
		self.assertNotEqual(doc.public_token_hash, created["token"])
		self.assertNotIn("secret", doc.target_url)
		self.assertIn("/website-doctor/report#audit=", created["report_url"])
		self.assertNotIn("?token=", created["report_url"])
		with self.assertRaises(frappe.PermissionError):
			audits.public_status(doc.name, "wrong-token")
		self.assertEqual(audits.public_status(doc.name, created["token"])["status"], "Requested")

	def test_public_status_does_not_open_non_public_audits(self):
		growth.configure_feature_flags({"website_doctor_internal_enabled": 1})
		with patch("frappe.enqueue"):
			created = audits.request_operator_audit("https://example.com")
		self.audit_names.append(created["audit"])
		with self.assertRaises(frappe.PermissionError):
			audits.public_status(created["audit"], created["token"])

	def test_public_follow_up_requires_consent_and_enters_existing_crm_once(self):
		created = self._complete_public_audit()
		growth.configure_website_doctor({"crm_workspace": self.created["workspace"]})
		values = {
			"full_name": "Website Owner", "email": f"doctor-{self.token}@example.com",
			"business_name": "Example Business", "phone": "+263 77 000 0000",
		}
		with self.assertRaises(frappe.ValidationError):
			audits.capture_public_lead(created["audit"], created["token"], values)
		values["consent"] = 1
		first = audits.capture_public_lead(created["audit"], created["token"], values)
		second = audits.capture_public_lead(created["audit"], created["token"], values)
		self.assertTrue(first["captured"])
		self.assertEqual(first, second)
		leads = frappe.get_all("AI Lead", filters={"tenant": self.created["engine_tenant"], "email": values["email"]})
		self.assertEqual(len(leads), 1)
		lead = frappe.get_doc("AI Lead", leads[0].name)
		details = frappe.parse_json(lead.dynamic_details)
		self.assertEqual(details["attribution"]["channel_code"], "WEBSITE_DOCTOR")
		self.assertEqual(details["website_doctor"]["audit"], created["audit"])
		self.assertEqual(frappe.db.get_value("VerityAI Website Audit", created["audit"], "follow_up_lead"), lead.name)
		self.assertEqual(frappe.db.count("VerityAI Consent Record", {"source": "Public Website Doctor"}), 1)
		channel = frappe.db.get_value("VerityAI Growth Channel", {"channel_code": "WEBSITE_DOCTOR"}, "name")
		events = frappe.get_all("VerityAI Growth Event", filters={"workspace": self.created["workspace"], "channel": channel, "object_name": lead.name}, pluck="event_type")
		self.assertIn("lead.captured", events)
		self.assertIn("audit.lead_captured", events)

	def test_public_follow_up_honours_suppression_and_crm_mapping(self):
		created = self._complete_public_audit()
		email = f"suppressed-doctor-{self.token}@example.com"
		values = {"full_name": "No Contact", "email": email, "business_name": "Private Business", "consent": 1}
		with self.assertRaises(frappe.ValidationError):
			audits.capture_public_lead(created["audit"], created["token"], values)
		growth.configure_website_doctor({"crm_workspace": self.created["workspace"]})
		channel = frappe.db.get_value("VerityAI Growth Channel", {"channel_code": "WEBSITE_DOCTOR"}, "name")
		growth.suppress(email, "Test opt-out", channel=channel, source="Public Website Doctor")
		with self.assertRaises(frappe.PermissionError):
			audits.capture_public_lead(created["audit"], created["token"], values)

	def test_public_report_uses_fragment_token_and_safe_dom_rendering(self):
		with open(frappe.get_app_path("verityai_saas", "www", "website_doctor_report.html"), encoding="utf-8") as handle:
			template = handle.read()
		with open(frappe.get_app_path("verityai_saas", "public", "js", "website_doctor.js"), encoding="utf-8") as handle:
			script = handle.read()
		self.assertIn('name="referrer" content="no-referrer"', template)
		self.assertIn('name="robots" content="noindex,nofollow,noarchive"', template)
		with open(frappe.get_app_path("verityai_saas", "hooks.py"), encoding="utf-8") as handle:
			hooks = handle.read()
		self.assertIn('"from_route": "/website-doctor/report"', hooks)
		self.assertIn("location.hash.slice(1)", script)
		self.assertIn('body.set("token", token)', script)
		self.assertNotIn("URLSearchParams({audit, token})", script)
		self.assertIn("textContent", script)
		self.assertNotIn("innerHTML", script)

	def test_operator_pilot_has_an_independent_kill_switch(self):
		growth.configure_feature_flags({"website_doctor_internal_enabled": 0})
		with self.assertRaises(frappe.PermissionError):
			audits.request_operator_audit("https://example.com")
		growth.configure_feature_flags({"website_doctor_internal_enabled": 1})
		with patch("frappe.enqueue"):
			created = audits.request_operator_audit("https://example.com")
		self.audit_names.append(created["audit"])
		self.assertEqual(created["status"], "Requested")

	def test_workspace_audit_completes_with_immutable_evidence_and_cost(self):
		growth.configure_feature_flags({"public_audits_enabled": 1})
		frappe.set_user(self.owner)
		with patch("frappe.enqueue"):
			created = audits.request_workspace_audit(self.created["workspace"], "https://example.com")
		self.audit_names.append(created["audit"])
		fetch = FetchResult(
			url="https://example.com/", status_code=200, headers={"content-type": "text/html"},
			body=b"<html lang='en'><head><title>Example Business Website</title></head><body><h1>Welcome</h1><button>Contact</button></body></html>",
			resolved_ip="93.184.216.34", duration_ms=25, redirect_count=0,
		)
		with patch("verityai_saas.growth.audits.fetch_public_html", return_value=fetch), patch(
			"verityai_saas.growth.audits.run_pagespeed",
			return_value=([{
				"category": "Performance",
				"check_code": "pagespeed_performance",
				"status": "Pass",
				"source": "PageSpeed",
				"summary": "PageSpeed performance score: 95.",
				"measured": {"score": 95},
				"recommendation": "",
			}], 120, 0.0025),
		):
			result = audits.process_audit(created["audit"])
		self.assertEqual(result["status"], "Completed")
		self.assertEqual(result["provider_duration_ms"], 120)
		self.assertGreater(len(result["findings"]), 5)
		doc = frappe.get_doc("VerityAI Website Audit", created["audit"])
		self.assertEqual(float(doc.provider_cost_usd), 0.0025)
		doc.overall_score = 100
		with self.assertRaises(frappe.PermissionError):
			doc.save(ignore_permissions=True)
		evidence = frappe.get_all("VerityAI Website Audit Evidence", filters={"audit": doc.name}, pluck="name")
		self.assertTrue(evidence)
		row = frappe.get_doc("VerityAI Website Audit Evidence", evidence[0])
		row.summary = "Tampered"
		with self.assertRaises(frappe.PermissionError):
			row.save(ignore_permissions=True)

	def test_workspace_api_blocks_cross_tenant_access(self):
		growth.configure_feature_flags({"public_audits_enabled": 1})
		with patch("frappe.enqueue"):
			created = audits.request_workspace_audit(self.created["workspace"], "https://example.com")
		self.audit_names.append(created["audit"])
		other_email = f"audit-other-{self.token}@example.com"
		frappe.get_doc({"doctype": "User", "email": other_email, "first_name": "Other", "user_type": "Website User", "send_welcome_email": 0}).insert(ignore_permissions=True)
		other = create_workspace(other_email, f"Other Audit Account {self.token}", f"Other Audit Workspace {self.token}")
		try:
			frappe.set_user(other_email)
			response = audit_api.detail_for_workspace(self.created["workspace"], created["audit"])
			self.assertFalse(response["success"])
			self.assertEqual(response["code"], "WORKSPACE_FORBIDDEN")
		finally:
			cleanup_test_workspace(other["workspace"], users=[other_email], engine_tenant=other["engine_tenant"], commit=False)
