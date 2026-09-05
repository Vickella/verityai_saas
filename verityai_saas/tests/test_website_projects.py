import copy

import frappe
from frappe.tests.utils import FrappeTestCase

from verityai_saas.api import websites as website_api
from verityai_saas.services import growth
from verityai_saas.services.onboarding import create_workspace
from verityai_saas.setup_doctypes import ensure_doctypes
from verityai_saas.tests.cleanup import cleanup_test_workspace
from verityai_saas.websites import projects


class TestWebsiteProjectFoundation(FrappeTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		ensure_doctypes()
		growth.seed_default_channels()
		self.original_flags = growth.feature_flags()
		self.token = frappe.generate_hash(length=8).lower()
		self.users = []
		self.workspaces = []
		self.created = self.create_test_workspace("owner")

	def tearDown(self):
		frappe.set_user("Administrator")
		for created in reversed(self.workspaces):
			cleanup_test_workspace(
				created["workspace"], users=[created["owner"]],
				engine_tenant=created["engine_tenant"], commit=False,
			)
		growth.configure_feature_flags(self.original_flags)
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
		growth.configure_feature_flags({"website_builder_enabled": 1})
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
