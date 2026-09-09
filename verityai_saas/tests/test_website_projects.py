import copy
import io
import json
import zipfile
import hashlib

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import now_datetime

from verityai_saas.api import websites as website_api
from verityai_saas.services import growth
from verityai_saas.services.onboarding import create_workspace
from verityai_saas.setup_doctypes import ensure_doctypes
from verityai_saas.tests.cleanup import cleanup_test_workspace
from verityai_saas.websites import projects
from verityai_saas.websites import templates


class TestWebsiteProjectFoundation(FrappeTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		ensure_doctypes()
		growth.seed_default_channels()
		self.original_flags = growth.feature_flags()
		self.token = frappe.generate_hash(length=8).lower()
		self.users = []
		self.workspaces = []
		self.template_keys = []
		self.created = self.create_test_workspace("owner")

	def tearDown(self):
		frappe.set_user("Administrator")
		for created in reversed(self.workspaces):
			cleanup_test_workspace(
				created["workspace"], users=[created["owner"]],
				engine_tenant=created["engine_tenant"], commit=False,
			)
		growth.configure_feature_flags(self.original_flags)
		for key in self.template_keys:
			name = frappe.db.get_value("VerityAI Website Template", {"template_key": key}, "name")
			if name:
				frappe.db.delete("File", {"attached_to_doctype": "VerityAI Website Template", "attached_to_name": name})
				frappe.db.delete("VerityAI Website Template", {"name": name})
		frappe.db.commit()

	def create_test_workspace(self, prefix):
		email = f"website-{prefix}-{self.token}@example.com"
		owner = frappe.get_doc({
			"doctype": "User", "email": email, "first_name": "Website", "last_name": "Tester",
			"user_type": "Website User", "send_welcome_email": 0,
		}).insert(ignore_permissions=True).name
		created = create_workspace(owner, f"Website Account {prefix} {self.token}", f"Website Workspace {prefix} {self.token}")
		created["owner"] = owner
		self.workspaces.append(created)
		return created

	@staticmethod
	def definition():
		return {
			"schema_version": 1,
			"site": {"title": "Acme Advisory", "description": "Practical business advice", "language": "en"},
			"brand": {"primary_color": "#2457d6", "background_color": "#ffffff"},
			"navigation": [{"label": "Home", "page_slug": "home"}],
			"pages": [{
				"slug": "home", "title": "Home", "description": "Welcome to Acme",
				"sections": [{
					"id": "hero-1", "type": "hero", "heading": "Grow with confidence",
					"body": "Clear advice for growing businesses.",
					"primary_action": {"label": "Talk to us", "url": "https://example.com/contact"},
				}],
			}],
			"integrations": {"widget_enabled": True, "whatsapp_enabled": False, "crm_enabled": True},
		}

	def test_customer_mutations_remain_disabled_by_default(self):
		growth.configure_feature_flags({"website_builder_enabled": 0})
		with self.assertRaises(frappe.PermissionError):
			projects.create_project(self.created["workspace"], {
				"project_name": "Blocked project", "project_slug": f"blocked-{self.token}",
			})

	def test_project_versions_are_structured_immutable_and_state_gated(self):
		growth.configure_feature_flags({"growth_foundation_enabled": 1, "website_builder_enabled": 1})
		project = projects.create_project(self.created["workspace"], {
			"project_name": "Acme website", "project_slug": f"acme-{self.token}",
			"definition": self.definition(), "widget_enabled": 1,
		})
		self.assertEqual(project["status"], "Draft")
		self.assertEqual(project["version_count"], 1)
		self.assertEqual(project["definition_version"], 1)
		self.assertEqual(project["definition"]["pages"][0]["slug"], "home")
		self.assertTrue(project["definition"]["integrations"]["widget_enabled"])

		duplicate = projects.add_definition_version(
			self.created["workspace"], project["name"], self.definition()
		)
		self.assertEqual(duplicate["name"], project["current_version"])
		self.assertEqual(frappe.db.count("VerityAI Website Definition Version", {"project": project["name"]}), 1)

		ready = projects.set_status(self.created["workspace"], project["name"], "Ready")
		self.assertEqual(ready["status"], "Ready")
		with self.assertRaises(frappe.ValidationError):
			projects.set_status(self.created["workspace"], project["name"], "Published")
		version = frappe.get_doc("VerityAI Website Definition Version", project["current_version"])
		version.source = "Import"
		with self.assertRaises(frappe.PermissionError):
			version.save(ignore_permissions=True)

		events = set(frappe.get_all(
			"VerityAI Growth Event", filters={"workspace": self.created["workspace"]}, pluck="event_type",
		))
		self.assertTrue({"website.project_created", "website.definition_version_created", "website.project_ready"}.issubset(events))

	def test_definition_rejects_executable_content_and_unknown_fields(self):
		growth.configure_feature_flags({"website_builder_enabled": 1})
		project = projects.create_project(self.created["workspace"], {
			"project_name": "Safe website", "project_slug": f"safe-{self.token}",
		})
		malicious = copy.deepcopy(self.definition())
		malicious["pages"][0]["sections"][0]["body"] = "<script>alert('x')</script>"
		with self.assertRaises(frappe.ValidationError):
			projects.add_definition_version(self.created["workspace"], project["name"], malicious)
		unknown = copy.deepcopy(self.definition())
		unknown["server_code"] = "run this"
		with self.assertRaises(frappe.ValidationError):
			projects.add_definition_version(self.created["workspace"], project["name"], unknown)

	def test_project_limit_and_workspace_scope_are_enforced(self):
		growth.configure_feature_flags({"website_builder_enabled": 1})
		project = projects.create_project(self.created["workspace"], {
			"project_name": "Only project", "project_slug": f"only-{self.token}",
		})
		with self.assertRaises(frappe.ValidationError):
			projects.create_project(self.created["workspace"], {
				"project_name": "Second project", "project_slug": f"second-{self.token}",
			})
		other = self.create_test_workspace("other")
		with self.assertRaises(frappe.DoesNotExistError):
			projects.get_project(other["workspace"], project["name"])

		frappe.set_user(other["owner"])
		response = website_api.detail(self.created["workspace"], project["name"])
		self.assertFalse(response["success"])
		self.assertEqual(response["code"], "WORKSPACE_FORBIDDEN")

	def test_ready_requires_a_validated_version_and_domains_are_locked(self):
		growth.configure_feature_flags({"website_builder_enabled": 1})
		project = projects.create_project(self.created["workspace"], {
			"project_name": "Draft project", "project_slug": f"draft-{self.token}",
		})
		with self.assertRaises(frappe.ValidationError):
			projects.set_status(self.created["workspace"], project["name"], "Ready")
		doc = frappe.get_doc("VerityAI Website Project", project["name"])
		doc.custom_domain = "customer.example.com"
		with self.assertRaises(frappe.ValidationError):
			doc.save(ignore_permissions=True)

	def test_catalogue_builds_a_tenant_branded_safe_definition(self):
		definition = templates.build_definition("community-v1", "Greater Grace Revival Ministries", "Church")
		self.assertEqual(definition["site"]["title"], "Greater Grace Revival Ministries")
		self.assertIn("Greater Grace Revival Ministries", definition["pages"][0]["sections"][0]["heading"])
		self.assertNotIn("VerityCore", json.dumps(definition))

	def test_create_from_template_generates_an_immutable_preview_version(self):
		growth.configure_feature_flags({"growth_foundation_enabled": 1, "website_builder_enabled": 1})
		project = projects.create_from_template(self.created["workspace"], {
			"project_name": "Community website", "project_slug": f"community-{self.token}",
			"template_key": "community-v1",
		})
		self.assertEqual(project["definition_version"], 1)
		self.assertEqual(project["template_key"], "community-v1")
		self.assertEqual(
			project["definition"]["site"]["title"],
			frappe.db.get_value("VerityAI Workspace", self.created["workspace"], "business_name"),
		)
		self.assertFalse(project["published_version"])

	def test_operator_zip_template_is_bounded_validated_and_available(self):
		key = f"custom-{self.token}"
		self.template_keys.append(key)
		manifest = {
			"key": key, "name": "Custom Advisory", "category": "Professional",
			"description": "A safe custom operator template.", "definition": self.definition(),
		}
		stream = io.BytesIO()
		with zipfile.ZipFile(stream, "w", zipfile.ZIP_DEFLATED) as archive:
			archive.writestr("template.json", json.dumps(manifest))
		stream.seek(0)
		stream.filename = "custom-template.zip"
		created = templates.upload_package(stream)
		self.assertEqual(created["key"], key)
		self.assertTrue(frappe.db.exists("VerityAI Website Template", {"template_key": key, "active": 1}))
		definition = templates.build_definition(key, "Tenant Brand", "Consulting")
		self.assertEqual(definition["site"]["title"], "Acme Advisory")

	def test_zip_template_rejects_traversal_and_executable_definition(self):
		stream = io.BytesIO()
		with zipfile.ZipFile(stream, "w") as archive:
			archive.writestr("../template.json", "{}")
		stream.seek(0)
		stream.filename = "unsafe.zip"
		with self.assertRaises(frappe.ValidationError):
			templates.upload_package(stream)

		malicious = self.definition()
		malicious["pages"][0]["sections"][0]["body"] = "<script>steal()</script>"
		stream = io.BytesIO()
		with zipfile.ZipFile(stream, "w") as archive:
			archive.writestr("template.json", json.dumps({
				"key": f"bad-{self.token}", "name": "Bad", "category": "Bad",
				"description": "Must be rejected", "definition": malicious,
			}))
		stream.seek(0)
		stream.filename = "bad.zip"
		with self.assertRaises(frappe.ValidationError):
			templates.upload_package(stream)

	def test_completed_workspace_audit_can_create_one_traceable_redesign(self):
		growth.configure_feature_flags({"website_builder_enabled": 1})
		now = now_datetime()
		audit = frappe.get_doc({
			"doctype": "VerityAI Website Audit", "workspace": self.created["workspace"],
			"target_url": "https://example.com/", "target_host": "example.com",
			"request_kind": "Workspace", "status": "Completed", "requested_by_user": self.created["owner"],
			"correlation_id": frappe.generate_hash(length=32),
			"public_token_hash": hashlib.sha256(b"test-token").hexdigest(),
			"observed_at": now, "completed_at": now, "overall_score": 72,
			"result_json": json.dumps({"category_scores": {}, "findings": []}),
		}).insert(ignore_permissions=True)
		project = projects.create_from_audit(self.created["workspace"], audit.name, {
			"project_name": "Evidence redesign", "project_slug": f"redesign-{self.token}",
			"template_key": "professional-v1",
		})
		self.assertEqual(project["source_audit"], audit.name)
		self.assertIn("example.com", project["definition"]["site"]["description"])
		self.assertEqual(
			frappe.db.get_value("VerityAI Website Definition Version", project["current_version"], "source"),
			"Website Doctor",
		)
		self.assertEqual(projects.create_from_audit(self.created["workspace"], audit.name, {})["name"], project["name"])

	def test_website_portal_and_operator_template_controls_are_present(self):
		from pathlib import Path
		root = Path(__file__).resolve().parents[1]
		portal = (root / "public" / "js" / "portal.js").read_text(encoding="utf-8")
		admin = (root / "public" / "js" / "admin.js").read_text(encoding="utf-8")
		self.assertIn("async function website()", portal)
		self.assertIn("websitePreview", portal)
		self.assertIn("upload_website_template", admin)
		self.assertIn("data-template-active", admin)
