import frappe


def execute():
	from verityai_saas.setup_doctypes import ensure_doctypes, ensure_workspace

	ensure_doctypes()
	ensure_workspace()
	# Existing owners should display their explicit full-access flags consistently
	# in the team UI. Role defaults still enforce access for Admin and Sales roles.
	frappe.db.sql(
		"""update `tabVerityAI Workspace Member`
		set can_view_campaigns=1, can_manage_campaigns=1
		where workspace_role='Owner'"""
	)
