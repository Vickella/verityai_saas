from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from verityai_saas import setup_doctypes
from verityai_saas.api import workspace as workspace_api
from verityai_saas.services.onboarding import create_workspace
from verityai_saas.services.billing import assign_plan
from verityai_saas.services.workspace import (
	add_member,
	remove_member,
	resend_member_invitation,
	update_member,
)
from verityai_saas.tests.cleanup import cleanup_all_test_fixtures, cleanup_test_workspace


class TestWorkspaceTeamManagement(FrappeTestCase):
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
		self.owner = self.create_user(f"team-owner-{token}@example.com")
		self.other = self.create_user(f"team-other-{token}@example.com")
		self.member_user = self.create_user(f"team-user-{token}@example.com")
		self.extra_users = []
		self.created = create_workspace(
			self.owner,
			f"Team Account {token}",
			f"Team Workspace {token}",
		)
		self.workspace = self.created["workspace"]
		self.tenant = self.created["engine_tenant"]
		launch_plan = frappe.db.get_value("VerityAI Plan", {"plan_code": "LAUNCH"}, "name")
		assign_plan(self.workspace, launch_plan, "Active", "Monthly")

	def tearDown(self):
		super().tearDown()
		cleanup_test_workspace(
			self.workspace,
			users=[self.owner, self.other, self.member_user, *self.extra_users],
			engine_tenant=self.tenant,
		)

	def create_user(self, email):
		return frappe.get_doc(
			{
				"doctype": "User",
				"email": email,
				"first_name": "Team",
				"last_name": "Tester",
				"user_type": "Website User",
				"send_welcome_email": 0,
			}
		).insert(ignore_permissions=True).name

	def test_member_role_permissions_removal_and_reactivation(self):
		member = add_member(self.workspace, self.member_user, "Viewer")
		self.assertIn("VerityAI Viewer", frappe.get_roles(self.member_user))

		update_member(
			self.workspace,
			member,
			role="Admin",
			permissions={"can_approve_quotes": 1, "can_manage_billing": 1},
		)
		self.assertEqual(
			frappe.db.get_value("VerityAI Workspace Member", member, "workspace_role"), "Admin"
		)
		self.assertEqual(
			frappe.db.get_value("VerityAI Workspace Member", member, "can_approve_quotes"), 1
		)
		self.assertIn("VerityAI Customer Admin", frappe.get_roles(self.member_user))
		self.assertNotIn("VerityAI Viewer", frappe.get_roles(self.member_user))

		remove_member(self.workspace, member)
		self.assertEqual(frappe.db.get_value("VerityAI Workspace Member", member, "status"), "Disabled")
		self.assertNotIn("VerityAI Customer Admin", frappe.get_roles(self.member_user))

		self.assertEqual(add_member(self.workspace, self.member_user, "Sales"), member)
		self.assertEqual(frappe.db.get_value("VerityAI Workspace Member", member, "status"), "Active")
		self.assertIn("VerityAI Sales User", frappe.get_roles(self.member_user))

	def test_workspace_owner_cannot_be_changed_or_removed(self):
		with self.assertRaises(frappe.ValidationError):
			update_member(self.workspace, self.created["member"], role="Viewer")
		with self.assertRaises(frappe.ValidationError):
			remove_member(self.workspace, self.created["member"])

	def test_non_manager_cannot_use_team_management_api(self):
		frappe.set_user(self.other)
		response = workspace_api.update(self.workspace, self.created["member"], role="Viewer")
		self.assertFalse(response["success"])
		self.assertEqual(response["code"], "WORKSPACE_FORBIDDEN")
		response = workspace_api.resend_invite(self.workspace, self.created["member"])
		self.assertFalse(response["success"])
		self.assertEqual(response["code"], "WORKSPACE_FORBIDDEN")

	def test_active_team_members_respect_plan_limit(self):
		add_member(self.workspace, self.member_user, "Viewer")
		second = self.create_user(f"team-user-{frappe.generate_hash(length=8).lower()}@example.com")
		third = self.create_user(f"team-user-{frappe.generate_hash(length=8).lower()}@example.com")
		self.extra_users.extend([second, third])
		add_member(self.workspace, second, "Support")

		with self.assertRaises(frappe.ValidationError):
			add_member(self.workspace, third, "Sales")

	@patch("verityai_saas.services.workspace.send_workspace_invitation")
	def test_new_member_receives_secure_workspace_invitation(self, send_invitation):
		email = f"team-invite-{frappe.generate_hash(length=8).lower()}@example.com"
		self.extra_users.append(email)

		member = add_member(self.workspace, email, "Support")

		self.assertTrue(frappe.db.exists("VerityAI Workspace Member", member))
		self.assertTrue(frappe.db.get_value("User", email, "reset_password_key"))
		send_invitation.assert_called_once()
		workspace_name, recipient, role, activation_link = send_invitation.call_args.args
		self.assertEqual(workspace_name, self.workspace)
		self.assertEqual(recipient, email)
		self.assertEqual(role, "Support")
		self.assertIn("/update-password?key=", activation_link)
		self.assertIn("redirect_to=", activation_link)

	@patch("verityai_saas.services.workspace.send_workspace_invitation")
	def test_reactivated_member_receives_fresh_invitation(self, send_invitation):
		member = add_member(self.workspace, self.member_user, "Viewer")
		remove_member(self.workspace, member)
		send_invitation.reset_mock()

		add_member(self.workspace, self.member_user, "Sales")

		send_invitation.assert_called_once_with(self.workspace, self.member_user, "Sales")

	@patch("verityai_saas.services.workspace.send_workspace_invitation")
	def test_active_member_invitation_can_be_resent(self, send_invitation):
		member = add_member(self.workspace, self.member_user, "Viewer")
		send_invitation.reset_mock()

		resend_member_invitation(self.workspace, member)

		send_invitation.assert_called_once()
		workspace_name, recipient, role, activation_link = send_invitation.call_args.args
		self.assertEqual((workspace_name, recipient, role), (self.workspace, self.member_user, "Viewer"))
		self.assertIn("/update-password?key=", activation_link)
