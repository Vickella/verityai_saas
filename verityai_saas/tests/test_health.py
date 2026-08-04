import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import now_datetime

from verityai_saas import setup_doctypes
from verityai_saas.api import health as health_api
from verityai_saas.services.health import workspace_health
from verityai_saas.services.onboarding import create_workspace
from verityai_saas.tests.cleanup import cleanup_all_test_fixtures, cleanup_test_workspace


class TestWorkspaceHealthPortal(FrappeTestCase):
	@classmethod
	def tearDownClass(cls):
		super().tearDownClass()
		cleanup_all_test_fixtures()

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		frappe.set_user("Administrator")
		setup_doctypes.install()

	def setUp(self):
		frappe.set_user("Administrator")
		token = frappe.generate_hash(length=8).lower()
		self.owner = self.create_user(f"health-owner-{token}@example.com")
		self.other = self.create_user(f"health-other-{token}@example.com")
		self.created = create_workspace(
			self.owner,
			f"Health Account {token}",
			f"Health Workspace {token}",
		)
		self.workspace = self.created["workspace"]
		self.tenant = self.created["engine_tenant"]

	def tearDown(self):
		super().tearDown()
		cleanup_test_workspace(self.workspace, users=[self.owner, self.other], engine_tenant=self.tenant)

	def create_user(self, email):
		return frappe.get_doc(
			{
				"doctype": "User",
				"email": email,
				"first_name": "Health",
				"last_name": "Tester",
				"user_type": "Website User",
				"send_welcome_email": 0,
			}
		).insert(ignore_permissions=True).name

	def create_alert(self, tenant=None, severity="Critical", status="Open"):
		now = now_datetime()
		return frappe.get_doc(
			{
				"doctype": "AI Monitoring Alert",
				"tenant": tenant or self.tenant,
				"alert_type": "System",
				"severity": severity,
				"status": status,
				"summary": "Provider health requires attention",
				"occurrence_count": 1,
				"first_seen": now,
				"last_seen": now,
			}
		).insert(ignore_permissions=True)

	def test_health_snapshot_is_tenant_scoped_and_safe(self):
		alert = self.create_alert()
		other_tenant = frappe.get_doc(
			{
				"doctype": "AI Tenant",
				"tenant_name": f"other-{frappe.generate_hash(length=8)}",
				"assistant_name": "Other",
				"active": 1,
			}
		).insert(ignore_permissions=True)
		self.create_alert(other_tenant.name)
		frappe.set_user(self.owner)

		data = workspace_health(self.workspace)

		self.assertEqual(data["overall_status"], "Critical")
		self.assertEqual(data["open_alerts"], 1)
		self.assertEqual(data["critical_alerts"], 1)
		self.assertEqual([row.name for row in data["alerts"]], [alert.name])
		self.assertNotIn("tenant", data["alerts"][0])

	def test_alert_filters_remain_tenant_scoped(self):
		open_alert = self.create_alert(severity="Warning")
		self.create_alert(severity="Info", status="Resolved")
		frappe.set_user(self.owner)

		data = workspace_health(self.workspace, status="Open", severity="Warning")

		self.assertEqual([row.name for row in data["alerts"]], [open_alert.name])

	def test_non_member_cannot_read_workspace_health(self):
		frappe.set_user(self.other)
		response = health_api.get(self.workspace)
		self.assertFalse(response["success"])
		self.assertEqual(response["code"], "WORKSPACE_FORBIDDEN")

	def test_operator_can_acknowledge_and_resolve_scoped_alert(self):
		alert = self.create_alert(severity="Warning")
		response = health_api.update_alert(self.workspace, alert.name, "Acknowledged", "Investigating provider latency")
		self.assertTrue(response["success"])
		self.assertEqual(frappe.db.get_value("AI Monitoring Alert", alert.name, "status"), "Acknowledged")
		details = frappe.parse_json(frappe.db.get_value("AI Monitoring Alert", alert.name, "details_json"))
		self.assertEqual(details["operator_notes"][0]["note"], "Investigating provider latency")
		response = health_api.update_alert(self.workspace, alert.name, "Resolved", "Provider recovered")
		self.assertTrue(response["success"])

	def test_customer_cannot_change_monitoring_alert_status(self):
		alert = self.create_alert(severity="Warning")
		frappe.set_user(self.owner)
		response = health_api.update_alert(self.workspace, alert.name, "Resolved")
		self.assertFalse(response["success"])
		self.assertEqual(response["code"], "WORKSPACE_FORBIDDEN")