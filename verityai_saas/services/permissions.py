import frappe
from frappe import _


OPERATOR_ROLES = {"System Manager", "VerityAI SaaS Administrator", "VerityAI Operator"}
ROLE_DEFAULTS = {
	"Owner": {"*"},
	"Admin": {"manage_assistant", "manage_widget", "manage_knowledge", "view_leads", "manage_leads", "view_conversations", "manage_conversations", "manage_billing", "manage_whatsapp", "manage_email", "manage_team", "approve_quotes", "view_customers", "manage_customers", "view_catalog", "manage_catalog", "view_quotes", "manage_quotes"},
	"Sales": {"view_leads", "manage_leads", "view_conversations", "view_customers", "manage_customers", "view_catalog", "view_quotes", "manage_quotes"},
	"Support": {"view_leads", "view_conversations", "manage_conversations"},
	"Viewer": {"view_leads", "view_conversations", "view_customers", "view_catalog", "view_quotes"},
	"Billing Manager": {"manage_billing"},
}


def current_user(user=None):
	return user or frappe.session.user


def is_operator(user=None):
	user = current_user(user)
	return user != "Guest" and bool(OPERATOR_ROLES.intersection(set(frappe.get_roles(user))))


def require_login(user=None):
	user = current_user(user)
	if not user or user == "Guest":
		frappe.throw(_("Login is required."), frappe.AuthenticationError)
	return user


def get_user_workspaces(user=None):
	user = require_login(user)
	if is_operator(user):
		return frappe.get_all("VerityAI Workspace", pluck="name", order_by="workspace_name asc")
	owned = frappe.get_all("VerityAI Workspace", filters={"owner_user": user}, pluck="name")
	memberships = frappe.get_all(
		"VerityAI Workspace Member", filters={"user": user, "status": "Active"}, pluck="workspace"
	)
	return sorted(set(owned + memberships))


def check_workspace_access(workspace_name, user=None):
	user = require_login(user)
	if not workspace_name or not frappe.db.exists("VerityAI Workspace", workspace_name):
		frappe.throw(_("Workspace was not found."), frappe.DoesNotExistError)
	if not is_operator(user) and workspace_name not in get_user_workspaces(user):
		frappe.throw(_("You do not have access to this workspace."), frappe.PermissionError)
	return frappe.get_doc("VerityAI Workspace", workspace_name)


def get_membership(workspace_name, user=None):
	user = current_user(user)
	rows = frappe.get_all(
		"VerityAI Workspace Member",
		filters={"workspace": workspace_name, "user": user, "status": "Active"},
		fields=["name", "workspace_role", "can_manage_assistant", "can_manage_widget", "can_manage_knowledge", "can_view_leads", "can_manage_leads", "can_view_conversations", "can_manage_conversations", "can_manage_billing", "can_manage_whatsapp", "can_manage_email", "can_approve_quotes", "can_view_customers", "can_manage_customers", "can_view_catalog", "can_manage_catalog", "can_view_quotes", "can_manage_quotes"],
		limit=1,
	)
	return rows[0] if rows else None


def check_workspace_role(workspace_name, allowed_roles, user=None):
	user = require_login(user)
	workspace = check_workspace_access(workspace_name, user)
	if is_operator(user):
		return True
	if workspace.owner_user == user:
		return "Owner" in set(allowed_roles)
	membership = get_membership(workspace_name, user)
	return bool(membership and membership.workspace_role in set(allowed_roles))


def require_workspace_permission(workspace_name, permission_key, user=None):
	user = require_login(user)
	workspace = check_workspace_access(workspace_name, user)
	if is_operator(user) or workspace.owner_user == user:
		return workspace
	membership = get_membership(workspace_name, user)
	if not membership:
		frappe.throw(_("You do not have access to this workspace."), frappe.PermissionError)
	role_permissions = ROLE_DEFAULTS.get(membership.workspace_role, set())
	fieldname = f"can_{permission_key}"
	if permission_key not in role_permissions and "*" not in role_permissions and not membership.get(fieldname):
		frappe.throw(_("Your workspace role does not allow this action."), frappe.PermissionError)
	return workspace


def sql_names(values):
	return ", ".join(frappe.db.escape(value) for value in values) or "''"


def workspace_query_condition(user=None):
	user = current_user(user)
	if is_operator(user):
		return ""
	return f"`tabVerityAI Workspace`.`name` in ({sql_names(get_user_workspaces(user))})"


def member_query_condition(user=None):
	user = current_user(user)
	if is_operator(user):
		return ""
	return f"`tabVerityAI Workspace Member`.`workspace` in ({sql_names(get_user_workspaces(user))})"


def account_query_condition(user=None):
	user = current_user(user)
	if is_operator(user):
		return ""
	accounts = frappe.get_all("VerityAI Workspace", filters={"name": ["in", get_user_workspaces(user)]}, pluck="account")
	return f"`tabVerityAI Account`.`name` in ({sql_names(accounts)})"


def workspace_child_query_condition(user=None):
	user = current_user(user)
	if is_operator(user):
		return ""
	return f"`workspace` in ({sql_names(get_user_workspaces(user))})"


def require_operator(user=None):
	user = require_login(user)
	if not is_operator(user):
		frappe.throw(_("Operator access is required."), frappe.PermissionError)
	return user
