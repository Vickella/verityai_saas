import frappe
from frappe.utils import now_datetime

from verityai_saas.services import engine
from verityai_saas.services.permissions import check_workspace_access


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
	return frappe.get_all("VerityAI Workspace Member", filters={"workspace": workspace_name}, fields=["name", "user", "workspace_role", "status", "creation"], order_by="creation asc")


def add_member(workspace_name, email, role="Viewer"):
	if not frappe.db.exists("User", email):
		user = frappe.get_doc({"doctype": "User", "email": email, "first_name": email.split("@", 1)[0], "send_welcome_email": 1, "user_type": "Website User"}).insert(ignore_permissions=True)
	else:
		user = frappe.get_doc("User", email)
	if frappe.db.exists("VerityAI Workspace Member", {"workspace": workspace_name, "user": user.name}):
		frappe.throw("This user is already a workspace member.", frappe.DuplicateEntryError)
	return frappe.get_doc({"doctype": "VerityAI Workspace Member", "workspace": workspace_name, "user": user.name, "workspace_role": role, "status": "Active"}).insert(ignore_permissions=True).name

