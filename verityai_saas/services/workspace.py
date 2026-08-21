from urllib.parse import quote

import frappe
from frappe.utils import now_datetime, validate_email_address

from verityai_saas.services import engine
from verityai_saas.services.permissions import check_workspace_access
from verityai_saas.services.platform_email import send_workspace_invitation
from verityai_saas.services.user_roles import assign_workspace_role, sync_workspace_roles

MEMBER_ROLES = {"Admin", "Sales", "Support", "Viewer", "Billing Manager"}
PERMISSION_FIELDS = (
	"can_manage_assistant",
	"can_manage_widget",
	"can_manage_knowledge",
	"can_view_leads",
	"can_manage_leads",
	"can_view_conversations",
	"can_manage_conversations",
	"can_manage_billing",
	"can_manage_whatsapp",
	"can_manage_email",
	"can_approve_quotes",
	"can_view_customers",
	"can_manage_customers",
	"can_view_catalog",
	"can_manage_catalog",
	"can_view_quotes",
	"can_manage_quotes",
)


def workspace_summary(workspace_name, user=None):
	workspace = check_workspace_access(workspace_name, user)
	checklist = frappe.get_all("VerityAI Onboarding Checklist", filters={"workspace": workspace.name}, fields=["step_code", "step_label", "status"], order_by="creation asc")
	subscriptions = frappe.get_all("VerityAI Subscription", filters={"workspace": workspace.name}, fields=["name", "plan", "status", "trial_end", "current_period_end", "next_billing_date"], order_by="creation desc", limit=1)
	wallet = frappe.db.get_value("VerityAI Usage Wallet", {"workspace": workspace.name}, ["tokens_used", "tokens_remaining", "status"], as_dict=True) or {}
	usage = engine.get_workspace_usage(workspace.name)
	tenant = engine.safe_settings(workspace.name) if workspace.engine_tenant else {}
	return {
		"workspace": {key: workspace.get(key) for key in ("name", "workspace_name", "business_name", "status", "onboarding_status", "setup_progress", "widget_installed", "engine_tenant")},
		"checklist": checklist,
		"subscription": subscriptions[0] if subscriptions else None,
		"wallet": wallet,
		"usage": usage,
		"assistant": tenant,
		"recent_alerts": engine.get_workspace_alerts(workspace.name),
		"conversation_count": frappe.db.count("AI Chat Session", {"tenant": workspace.engine_tenant}) if workspace.engine_tenant else 0,
		"new_leads": frappe.db.count("AI Lead", {"tenant": workspace.engine_tenant, "status": "New"}) if workspace.engine_tenant else 0,
		"generated_at": now_datetime(),
	}


def list_members(workspace_name, user=None):
	check_workspace_access(workspace_name, user)
	return frappe.get_all(
		"VerityAI Workspace Member",
		filters={"workspace": workspace_name},
		fields=["name", "user", "workspace_role", "status", *PERMISSION_FIELDS, "creation"],
		order_by="creation asc",
	)


def add_member(workspace_name, email, role="Viewer"):
	role = _validate_member_role(role)
	email = str(email or "").strip().lower()
	if not validate_email_address(email):
		frappe.throw("Please enter a valid email address.", frappe.ValidationError)
	existing_name = frappe.db.get_value(
		"VerityAI Workspace Member", {"workspace": workspace_name, "user": email}, "name"
	)
	if existing_name:
		existing = frappe.get_doc("VerityAI Workspace Member", existing_name)
		if existing.status == "Active":
			frappe.throw("This user is already an active workspace member.", frappe.DuplicateEntryError)
		_check_team_limit(workspace_name)
		existing.workspace_role = role
		existing.status = "Active"
		existing.save(ignore_permissions=True)
		sync_workspace_roles(existing.user)
		send_workspace_invitation(workspace_name, existing.user, role)
		return existing.name
	_check_team_limit(workspace_name)
	is_new_user = not frappe.db.exists("User", email)
	if is_new_user:
		user = frappe.get_doc(
			{
				"doctype": "User",
				"email": email,
				"first_name": email.split("@", 1)[0],
				"send_welcome_email": 0,
				"user_type": "Website User",
			}
		).insert(ignore_permissions=True)
	else:
		user = frappe.get_doc("User", email)
	member = frappe.get_doc(
		{
			"doctype": "VerityAI Workspace Member",
			"workspace": workspace_name,
			"user": user.name,
			"workspace_role": role,
			"status": "Active",
		}
	).insert(ignore_permissions=True)
	assign_workspace_role(user.name, role)
	activation_link = None
	if is_new_user:
		activation_link = _workspace_activation_link(user, workspace_name)
	send_workspace_invitation(workspace_name, user.name, role, activation_link)
	return member.name


def resend_member_invitation(workspace_name, member_name):
	member = _member_doc(workspace_name, member_name)
	if member.status != "Active":
		frappe.throw("Reactivate this member before sending an invitation.", frappe.ValidationError)
	user = frappe.get_doc("User", member.user)
	activation_link = _workspace_activation_link(user, workspace_name)
	send_workspace_invitation(
		workspace_name,
		user.name,
		member.workspace_role,
		activation_link,
	)
	return member.name


def _workspace_activation_link(user, workspace_name):
	activation_link = user._reset_password()
	redirect_path = f"/verityai?workspace={quote(workspace_name, safe='')}"
	return f"{activation_link}&redirect_to={quote(redirect_path, safe='')}"


def update_member(workspace_name, member_name, role=None, permissions=None):
	member = _member_doc(workspace_name, member_name)
	_assert_not_owner(workspace_name, member)
	if role is not None:
		member.workspace_role = _validate_member_role(role)
	permissions = permissions or {}
	if not isinstance(permissions, dict):
		frappe.throw("Member permissions must be an object.", frappe.ValidationError)
	unsupported = set(permissions) - set(PERMISSION_FIELDS)
	if unsupported:
		frappe.throw("Unsupported member permission.", frappe.ValidationError)
	for fieldname, value in permissions.items():
		member.set(fieldname, _check_value(value))
	member.save(ignore_permissions=True)
	sync_workspace_roles(member.user)
	return member.name


def remove_member(workspace_name, member_name):
	member = _member_doc(workspace_name, member_name)
	_assert_not_owner(workspace_name, member)
	member.status = "Disabled"
	member.save(ignore_permissions=True)
	sync_workspace_roles(member.user)
	return member.name


def _member_doc(workspace_name, member_name):
	if not frappe.db.exists(
		"VerityAI Workspace Member", {"name": member_name, "workspace": workspace_name}
	):
		frappe.throw("Workspace member was not found.", frappe.DoesNotExistError)
	return frappe.get_doc("VerityAI Workspace Member", member_name)


def _assert_not_owner(workspace_name, member):
	owner = frappe.db.get_value("VerityAI Workspace", workspace_name, "owner_user")
	if member.user == owner or member.workspace_role == "Owner":
		frappe.throw("The workspace owner cannot be changed or removed.", frappe.ValidationError)


def _validate_member_role(role):
	role = str(role or "").strip()
	if role not in MEMBER_ROLES:
		frappe.throw("Unsupported workspace role.", frappe.ValidationError)
	return role


def _check_value(value):
	if isinstance(value, str):
		return int(value.strip().lower() in {"1", "true", "yes", "on"})
	return int(bool(value))


def _check_team_limit(workspace_name):
	plan = frappe.db.get_value(
		"VerityAI Subscription",
		{"workspace": workspace_name},
		"plan",
		order_by="creation desc",
	)
	limit = int(frappe.db.get_value("VerityAI Plan", plan, "max_team_members") or 0) if plan else 0
	if limit and frappe.db.count(
		"VerityAI Workspace Member", {"workspace": workspace_name, "status": "Active"}
	) >= limit:
		frappe.throw(f"Your plan allows up to {limit} active team members.", frappe.ValidationError)
