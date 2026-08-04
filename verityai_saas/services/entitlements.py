import frappe
from frappe.utils import cint


ACTIVE_SUBSCRIPTION_STATUSES = {"Trial", "Active"}


def workspace_context(workspace_name=None, tenant=None):
	if not workspace_name and tenant:
		workspace_name = frappe.db.get_value("VerityAI Workspace", {"engine_tenant": tenant}, "name")
	if not workspace_name:
		return None
	workspace = frappe.db.get_value(
		"VerityAI Workspace",
		workspace_name,
		["name", "account", "engine_tenant", "status"],
		as_dict=True,
	)
	if not workspace:
		return None
	subscription = frappe.db.get_value(
		"VerityAI Subscription",
		{"workspace": workspace.name},
		["name", "plan", "status", "billing_cycle", "current_period_end", "trial_end", "grace_period_end"],
		as_dict=True,
		order_by="creation desc",
	)
	wallet = frappe.db.get_value(
		"VerityAI Usage Wallet",
		{"workspace": workspace.name},
		["name", "period_start", "period_end", "tokens_remaining", "status"],
		as_dict=True,
	)
	plan = frappe.get_doc("VerityAI Plan", subscription.plan) if subscription and subscription.plan else None
	return frappe._dict(workspace=workspace, subscription=subscription, wallet=wallet, plan=plan)


def _denied(message, code):
	return {"allowed": False, "message": message, "code": code}


def subscription_entitled(context):
	if not context or not context.subscription:
		return False
	if context.subscription.status in ACTIVE_SUBSCRIPTION_STATUSES:
		return True
	return bool(
		context.subscription.status == "Past Due"
		and context.subscription.grace_period_end
		and frappe.utils.getdate(context.subscription.grace_period_end) >= frappe.utils.getdate(frappe.utils.today())
	)

def feature_allowed(context, feature):
	if not context or not context.subscription or not context.plan:
		return False
	if context.subscription.status == "Trial":
		return True
	return bool(context.plan.get(feature))


def require_workspace_feature(workspace_name, feature, label=None):
	context = workspace_context(workspace_name=workspace_name)
	if not context or not context.subscription or not subscription_entitled(context):
		frappe.throw("An active subscription is required.", frappe.PermissionError)
	if not feature_allowed(context, feature):
		frappe.throw(f"Your plan does not include {label or feature.replace('_', ' ')}.", frappe.PermissionError)
	return context


def _channel_usage(context, platform):
	if not frappe.db.exists("DocType", "AI Usage Log"):
		return 0
	start = context.wallet.period_start if context.wallet and context.wallet.period_start else frappe.utils.get_first_day(frappe.utils.today())
	if platform == "Web":
		return cint(frappe.db.sql(
			"""select count(distinct chat_session) from `tabAI Usage Log`
			where tenant=%s and platform='Web' and creation >= %s and status != 'Error'""",
			(context.workspace.engine_tenant, start),
		)[0][0])
	return cint(frappe.db.count("AI Usage Log", {
		"tenant": context.workspace.engine_tenant,
		"platform": platform,
		"creation": [">=", start],
		"status": ["!=", "Error"],
	}))


def check_engine_request(tenant, platform, user_identifier=None):
	context = workspace_context(tenant=tenant)
	if not context:
		return {"allowed": True}
	if platform == "Desk":
		return {"allowed": True}
	if not context.subscription or not subscription_entitled(context):
		return _denied("This assistant is unavailable because its subscription is inactive.", "SUBSCRIPTION_INACTIVE")
	if context.workspace.status not in {"Trial", "Active"}:
		return _denied("This assistant is temporarily suspended.", "WORKSPACE_SUSPENDED")
	if not context.wallet or context.wallet.status in {"Exhausted", "Suspended"} or cint(context.wallet.tokens_remaining) <= 0:
		return _denied("This assistant has reached its current usage allowance.", "WALLET_EXHAUSTED")
	if platform == "WhatsApp" and not feature_allowed(context, "can_use_whatsapp_ai"):
		return _denied("WhatsApp AI is not included in this workspace plan.", "CHANNEL_NOT_INCLUDED")
	limit_field = "monthly_web_conversations" if platform == "Web" else "monthly_whatsapp_messages" if platform == "WhatsApp" else None
	limit = cint(context.plan.get(limit_field)) if limit_field else 0
	if limit > 0 and _channel_usage(context, platform) >= limit:
		return _denied(f"The monthly {platform} allowance has been reached.", "CHANNEL_QUOTA_EXHAUSTED")
	return {"allowed": True}


def email_delivery_allowance(workspace_name):
	context = workspace_context(workspace_name=workspace_name)
	if not context or not context.subscription or not subscription_entitled(context):
		return 0
	if not feature_allowed(context, "can_use_email_notifications"):
		return 0
	limit = cint(context.plan.monthly_email_sends)
	if limit <= 0:
		return None
	start = context.wallet.period_start if context.wallet and context.wallet.period_start else frappe.utils.get_first_day(frappe.utils.today())
	sent = frappe.db.count("VerityAI Email Delivery Log", {
		"workspace": workspace_name,
		"status": "Sent",
		"creation": [">=", start],
	})
	return max(limit - cint(sent), 0)


def assert_account_capacity(account_name, plan_name=None):
	workspace_names = frappe.get_all("VerityAI Workspace", filters={"account": account_name}, pluck="name")
	if not workspace_names:
		return
	if not plan_name:
		plan_name = frappe.db.get_value(
			"VerityAI Subscription",
			{"workspace": ["in", workspace_names], "status": ["in", list(ACTIVE_SUBSCRIPTION_STATUSES)]},
			"plan",
			order_by="creation desc",
		)
	if not plan_name:
		frappe.throw("An active plan is required to add another workspace.", frappe.PermissionError)
	plan = frappe.get_doc("VerityAI Plan", plan_name)
	workspace_limit = cint(plan.max_workspaces)
	assistant_limit = cint(plan.max_assistants)
	count = len(workspace_names)
	if workspace_limit > 0 and count >= workspace_limit:
		frappe.throw(f"Your plan allows up to {workspace_limit} workspace(s).", frappe.ValidationError)
	if assistant_limit > 0 and count >= assistant_limit:
		frappe.throw(f"Your plan allows up to {assistant_limit} assistant(s).", frappe.ValidationError)