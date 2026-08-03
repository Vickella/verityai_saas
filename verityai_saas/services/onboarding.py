import frappe
from frappe import _
from frappe.utils import add_days, today

from verityai_saas.services import engine
from verityai_saas.services.user_roles import assign_workspace_role


CHECKLIST = (
	("workspace", "Create Workspace"), ("assistant", "Create Assistant"), ("business_nature", "Set Business Nature"),
	("domain", "Add Website Domain"), ("widget", "Customize Widget"), ("test_widget", "Test Widget"),
	("knowledge", "Add Knowledge"), ("lead_capture", "Configure Lead Capture"), ("email", "Configure Email Notifications"),
	("whatsapp", "Configure WhatsApp"), ("install_widget", "Install Widget"), ("first_lead", "Capture First Lead"), ("plan", "Choose Plan"),
)


def slug_name(value):
	base = frappe.scrub(value).replace("_", "-")[:100]
	name, index = base, 2
	while frappe.db.exists("VerityAI Workspace", name):
		name, index = f"{base}-{index}", index + 1
	return name


def ensure_account(owner_user, account_name, billing_email=None, values=None):
	existing = frappe.db.get_value("VerityAI Account", {"owner_user": owner_user, "account_name": account_name}, "name")
	if existing:
		return existing
	values = values or {}
	return frappe.get_doc({"doctype": "VerityAI Account", "account_name": account_name, "owner_user": owner_user, "billing_email": billing_email or owner_user, "phone": values.get("phone"), "country": values.get("country"), "currency": values.get("currency") or "USD", "status": "Active", "customer_type": values.get("customer_type") or "SME"}).insert(ignore_permissions=True).name


def create_workspace(owner_user, account_name, workspace_name, business_name=None, plan_name=None, values=None):
	if not owner_user or owner_user == "Guest" or not frappe.db.exists("User", owner_user):
		frappe.throw(_("A valid owner user is required."), frappe.ValidationError)
	values = values or {}
	savepoint = f"verityai_onboarding_{frappe.generate_hash(length=8)}"
	frappe.db.savepoint(savepoint)
	try:
		account = ensure_account(owner_user, account_name, values.get("billing_email"), values)
		workspace = frappe.get_doc({"doctype": "VerityAI Workspace", "workspace_name": slug_name(workspace_name), "account": account, "owner_user": owner_user, "business_name": business_name or workspace_name, "business_nature": values.get("business_nature"), "website_url": values.get("website_url"), "country": values.get("country"), "currency": values.get("currency") or "USD", "timezone": values.get("timezone") or "Africa/Harare", "status": "Trial", "onboarding_status": "In Progress"}).insert(ignore_permissions=True)
		member = frappe.get_doc({"doctype": "VerityAI Workspace Member", "workspace": workspace.name, "user": owner_user, "workspace_role": "Owner", "status": "Active", "can_manage_assistant": 1, "can_manage_widget": 1, "can_manage_knowledge": 1, "can_view_leads": 1, "can_manage_leads": 1, "can_view_conversations": 1, "can_manage_billing": 1, "can_manage_whatsapp": 1, "can_manage_email": 1, "can_approve_quotes": 1}).insert(ignore_permissions=True)
		assign_workspace_role(owner_user, "Owner")
		tenant = engine.create_engine_tenant(workspace.name)
		configuration = engine.ensure_engine_configuration(workspace.name)
		plan_name = plan_name or frappe.db.get_value("VerityAI Plan", {"plan_code": "TRIAL", "active": 1}, "name") or frappe.db.get_value("VerityAI Plan", {"active": 1}, "name")
		if not plan_name:
			frappe.throw(_("No active SaaS plan is configured."), frappe.ValidationError)
		plan = frappe.get_doc("VerityAI Plan", plan_name)
		start, end = today(), add_days(today(), int(plan.trial_days or 14))
		subscription = frappe.get_doc({"doctype": "VerityAI Subscription", "account": account, "workspace": workspace.name, "plan": plan.name, "status": "Trial", "billing_cycle": "Monthly", "trial_start": start, "trial_end": end, "current_period_start": start, "current_period_end": end, "next_billing_date": end, "amount": plan.monthly_price, "currency": plan.currency}).insert(ignore_permissions=True)
		wallet = frappe.get_doc({"doctype": "VerityAI Usage Wallet", "workspace": workspace.name, "subscription": subscription.name, "period_start": start, "period_end": end, "opening_token_allowance": plan.monthly_token_limit or 0, "tokens_remaining": plan.monthly_token_limit or 0, "status": "Normal"}).insert(ignore_permissions=True)
		for code, label in CHECKLIST:
			done = code in {"workspace", "assistant", "plan"}
			frappe.get_doc({"doctype": "VerityAI Onboarding Checklist", "workspace": workspace.name, "step_code": code, "step_label": label, "status": "Done" if done else "Not Started", "completed_by": owner_user if done else None}).insert(ignore_permissions=True)
		frappe.get_doc({"doctype": "VerityAI Notification Setting", "workspace": workspace.name, "notification_email": values.get("billing_email") or owner_user, "lead_notifications_enabled": 1, "human_handoff_alerts_enabled": 1, "usage_warning_alerts_enabled": 1, "status": "Active"}).insert(ignore_permissions=True)
		frappe.get_doc({"doctype": "VerityAI WhatsApp Setup", "workspace": workspace.name, "mode": "Button Only", "setup_status": "Not Configured"}).insert(ignore_permissions=True)
		engine.apply_plan_limits(workspace.name, plan.name)
		frappe.db.set_value("VerityAI Account", account, "default_workspace", workspace.name)
		update_progress(workspace.name)
		return {"workspace": workspace.name, "account": account, "member": member.name, "engine_tenant": tenant, "engine_configuration": configuration, "subscription": subscription.name, "wallet": wallet.name, "dashboard_url": f"/verityai/dashboard?workspace={workspace.name}"}
	except Exception:
		frappe.db.rollback(save_point=savepoint)
		raise


def set_step(workspace_name, step_code, status="Done", user=None):
	name = frappe.db.get_value("VerityAI Onboarding Checklist", {"workspace": workspace_name, "step_code": step_code}, "name")
	if not name:
		frappe.throw(_("Onboarding step was not found."), frappe.DoesNotExistError)
	frappe.db.set_value("VerityAI Onboarding Checklist", name, {"status": status, "completed_on": frappe.utils.now_datetime() if status == "Done" else None, "completed_by": (user or frappe.session.user) if status == "Done" else None})
	return update_progress(workspace_name)


def update_progress(workspace_name):
	rows = frappe.get_all("VerityAI Onboarding Checklist", filters={"workspace": workspace_name}, pluck="status")
	progress = round((sum(status in {"Done", "Skipped"} for status in rows) / len(rows)) * 100, 2) if rows else 0
	frappe.db.set_value("VerityAI Workspace", workspace_name, {"setup_progress": progress, "onboarding_status": "Complete" if progress >= 100 else "In Progress"})
	return progress

