import frappe


MODULE = "VerityAI SaaS"
ADMIN_ROLE = "VerityAI SaaS Administrator"
OPERATOR_ROLE = "VerityAI Operator"
CUSTOMER_ROLES = (
	"VerityAI Customer Owner",
	"VerityAI Customer Admin",
	"VerityAI Sales User",
	"VerityAI Support User",
	"VerityAI Billing User",
	"VerityAI Viewer",
)


def install():
	ensure_roles()
	ensure_module()
	ensure_doctypes()
	ensure_default_plan()
	frappe.db.commit()


def ensure_roles():
	for role in (ADMIN_ROLE, OPERATOR_ROLE, *CUSTOMER_ROLES):
		if not frappe.db.exists("Role", role):
			frappe.get_doc(
				{"doctype": "Role", "role_name": role, "desk_access": int(role in {ADMIN_ROLE, OPERATOR_ROLE})}
			).insert(ignore_permissions=True)


def ensure_module():
	if not frappe.db.exists("Module Def", MODULE):
		frappe.get_doc({"doctype": "Module Def", "module_name": MODULE, "app_name": "verityai_saas"}).insert(
			ignore_permissions=True
		)


def permissions():
	full = {"read": 1, "write": 1, "create": 1, "delete": 1, "report": 1, "export": 1}
	return [{"role": "System Manager", **full}, {"role": ADMIN_ROLE, **full}, {"role": OPERATOR_ROLE, "read": 1, "report": 1, "export": 1}]


def field(fieldname, label, fieldtype="Data", **values):
	return {"fieldname": fieldname, "label": label, "fieldtype": fieldtype, **values}


def ensure_doctype(name, fields, autoname=None):
	values = {
		"module": MODULE,
		"custom": 1,
		"istable": 0,
		"track_changes": 1,
		"allow_import": 1,
		"fields": [{**row, **({"default": str(row["default"])} if row.get("default") is not None else {})} for row in fields],
		"permissions": permissions(),
	}
	if autoname:
		values["autoname"] = autoname
	if frappe.db.exists("DocType", name):
		doc = frappe.get_doc("DocType", name)
		existing = {row.fieldname: row for row in doc.fields}
		for row in values["fields"]:
			if row["fieldname"] in existing:
				for key, value in row.items():
					setattr(existing[row["fieldname"]], key, value)
			else:
				doc.append("fields", row)
		doc.permissions = []
		for row in values["permissions"]:
			doc.append("permissions", row)
		for key in ("module", "track_changes", "allow_import", "autoname"):
			if key in values:
				setattr(doc, key, values[key])
		doc.flags.ignore_version = True
		doc.save(ignore_permissions=True)
		return
	frappe.get_doc({"doctype": "DocType", "name": name, **values}).insert(ignore_permissions=True)


def ensure_doctypes():
	ensure_doctype("VerityAI Account", [
		field("account_name", "Account Name", reqd=1, unique=1, in_list_view=1),
		field("owner_user", "Owner User", "Link", options="User", reqd=1),
		field("billing_email", "Billing Email", options="Email", reqd=1), field("phone", "Phone"),
		field("country", "Country", "Link", options="Country"), field("currency", "Currency", "Link", options="Currency"),
		field("status", "Status", "Select", options="Active\nSuspended\nCancelled", default="Active", in_list_view=1),
		field("customer_type", "Customer Type", "Select", options="SME\nAgency\nEnterprise", default="SME"),
		field("notes", "Notes", "Small Text"),
	], "field:account_name")

	ensure_doctype("VerityAI Workspace", [
		field("workspace_name", "Workspace Name", reqd=1, unique=1, in_list_view=1),
		field("account", "Account", "Link", options="VerityAI Account", reqd=1, in_list_view=1),
		field("owner_user", "Owner User", "Link", options="User", reqd=1),
		field("engine_tenant", "Engine Tenant", "Link", options="AI Tenant", unique=1, in_list_view=1),
		field("business_name", "Business Name", reqd=1), field("business_nature", "Business Nature", "Link", options="AI Business Nature"),
		field("website_url", "Website URL"), field("country", "Country", "Link", options="Country"),
		field("currency", "Currency", "Link", options="Currency"), field("timezone", "Timezone", default="Africa/Harare"),
		field("status", "Status", "Select", options="Draft\nTrial\nActive\nSuspended\nCancelled", default="Draft", in_list_view=1),
		field("onboarding_status", "Onboarding Status", "Select", options="Not Started\nIn Progress\nComplete", default="Not Started"),
		field("setup_progress", "Setup Progress", "Percent", default=0), field("widget_installed", "Widget Installed", "Check", default=0),
		field("first_lead_captured", "First Lead Captured", "Check", default=0),
	], "field:workspace_name")

	# Add the reverse link only after Workspace exists; Frappe validates Link targets on creation.
	ensure_doctype("VerityAI Account", [
		field("default_workspace", "Default Workspace", "Link", options="VerityAI Workspace"),
	])

	ensure_doctype("VerityAI Workspace Member", [
		field("workspace", "Workspace", "Link", options="VerityAI Workspace", reqd=1, in_list_view=1),
		field("user", "User", "Link", options="User", reqd=1, in_list_view=1),
		field("workspace_role", "Workspace Role", "Select", options="Owner\nAdmin\nSales\nSupport\nViewer\nBilling Manager", reqd=1, in_list_view=1),
		field("status", "Status", "Select", options="Active\nInvited\nDisabled", default="Active"),
		*[field(key, label, "Check", default=0) for key, label in (
			("can_manage_assistant", "Can Manage Assistant"), ("can_manage_widget", "Can Manage Widget"),
			("can_manage_knowledge", "Can Manage Knowledge"), ("can_view_leads", "Can View Leads"),
			("can_manage_leads", "Can Manage Leads"), ("can_view_conversations", "Can View Conversations"),
			("can_manage_billing", "Can Manage Billing"), ("can_manage_whatsapp", "Can Manage WhatsApp"),
			("can_manage_email", "Can Manage Email"), ("can_approve_quotes", "Can Approve Quotes"),
		)],
	], "hash")

	ensure_doctype("VerityAI Plan", [
		field("plan_name", "Plan Name", reqd=1, unique=1, in_list_view=1), field("plan_code", "Plan Code", reqd=1, unique=1),
		field("active", "Active", "Check", default=1), field("currency", "Currency", "Link", options="Currency", default="USD"),
		field("monthly_price", "Monthly Price", "Currency"), field("annual_price", "Annual Price", "Currency"), field("trial_days", "Trial Days", "Int", default=14),
		field("max_workspaces", "Max Workspaces", "Int", default=1), field("max_assistants", "Max Assistants", "Int", default=1), field("max_team_members", "Max Team Members", "Int", default=3),
		field("monthly_token_limit", "Monthly Token Limit", "Int", default=100000), field("max_tokens", "Max Response Tokens", "Int", default=900),
		field("public_rate_limit_per_minute", "Public Rate Limit Per Minute", "Int", default=20), field("max_public_message_chars", "Max Public Message Characters", "Int", default=4000),
		field("monthly_web_conversations", "Monthly Web Conversations", "Int"), field("monthly_whatsapp_messages", "Monthly WhatsApp Messages", "Int"),
		field("monthly_email_sends", "Monthly Email Sends", "Int"), field("max_knowledge_sources", "Max Knowledge Sources", "Int", default=10), field("max_allowed_domains", "Max Allowed Domains", "Int", default=2),
		*[field(key, label, "Check", default=0) for key, label in (
			("can_remove_branding", "Can Remove Branding"), ("can_use_whatsapp_button", "Can Use WhatsApp Button"),
			("can_use_whatsapp_ai", "Can Use WhatsApp AI"), ("can_use_email_notifications", "Can Use Email Notifications"),
			("can_use_custom_smtp", "Can Use Custom SMTP"), ("can_use_erpnext_integration", "Can Use ERPNext Integration"),
			("can_use_quotation_workflow", "Can Use Quotation Workflow"), ("can_use_api_access", "Can Use API Access"),
			("can_bring_own_ai_provider_key", "Can Bring Own AI Provider Key"),
		)], field("support_level", "Support Level", "Select", options="Community\nStandard\nPriority", default="Standard"),
	], "field:plan_code")

	ensure_doctype("VerityAI Subscription", [
		field("account", "Account", "Link", options="VerityAI Account", reqd=1), field("workspace", "Workspace", "Link", options="VerityAI Workspace", reqd=1, in_list_view=1),
		field("plan", "Plan", "Link", options="VerityAI Plan", reqd=1, in_list_view=1), field("status", "Status", "Select", options="Trial\nActive\nPast Due\nSuspended\nCancelled\nExpired", default="Trial", in_list_view=1),
		field("billing_cycle", "Billing Cycle", "Select", options="Monthly\nAnnual\nManual", default="Monthly"), field("trial_start", "Trial Start", "Date"), field("trial_end", "Trial End", "Date"),
		field("current_period_start", "Current Period Start", "Date"), field("current_period_end", "Current Period End", "Date"), field("next_billing_date", "Next Billing Date", "Date"),
		field("amount", "Amount", "Currency"), field("currency", "Currency", "Link", options="Currency"), field("auto_renew", "Auto Renew", "Check", default=0),
		field("grace_period_end", "Grace Period End", "Date"), field("last_payment_reference", "Last Payment Reference"), field("suspension_reason", "Suspension Reason", "Small Text"),
	], "VSUB-.#####")

	ensure_doctype("VerityAI Usage Wallet", [
		field("workspace", "Workspace", "Link", options="VerityAI Workspace", reqd=1, unique=1, in_list_view=1), field("subscription", "Subscription", "Link", options="VerityAI Subscription", reqd=1),
		field("period_start", "Period Start", "Date"), field("period_end", "Period End", "Date"), field("opening_token_allowance", "Opening Token Allowance", "Int"),
		field("top_up_tokens", "Top-Up Tokens", "Int"), field("tokens_used", "Tokens Used", "Int"), field("tokens_remaining", "Tokens Remaining", "Int"),
		field("web_conversations_used", "Web Conversations Used", "Int"), field("whatsapp_messages_used", "WhatsApp Messages Used", "Int"), field("email_sends_used", "Email Sends Used", "Int"),
		field("estimated_ai_cost", "Estimated AI Cost", "Currency"), field("estimated_revenue", "Estimated Revenue", "Currency"), field("estimated_gross_margin", "Estimated Gross Margin", "Currency"),
		field("status", "Status", "Select", options="Normal\nWarning\nExhausted\nSuspended", default="Normal"), field("last_synced_from_usage_logs", "Last Synced From Usage Logs", "Datetime"),
	], "VWAL-.#####")

	ensure_doctype("VerityAI Usage Transaction", [
		field("workspace", "Workspace", "Link", options="VerityAI Workspace", reqd=1, in_list_view=1), field("engine_tenant", "Engine Tenant", "Link", options="AI Tenant", reqd=1),
		field("ai_usage_log", "AI Usage Log", "Link", options="AI Usage Log", unique=1), field("transaction_type", "Transaction Type", "Select", options="Usage\nBlocked\nTop-Up\nAdjustment\nRefund", reqd=1),
		field("platform", "Platform"), field("input_tokens", "Input Tokens", "Int"), field("output_tokens", "Output Tokens", "Int"), field("total_tokens", "Total Tokens", "Int"),
		field("estimated_cost", "Estimated Cost", "Currency"), field("billable_amount", "Billable Amount", "Currency"), field("period", "Period"),
	], "VUTX-.########")

	ensure_doctype("VerityAI Billing Event", [
		field("account", "Account", "Link", options="VerityAI Account", reqd=1), field("workspace", "Workspace", "Link", options="VerityAI Workspace", reqd=1, in_list_view=1),
		field("subscription", "Subscription", "Link", options="VerityAI Subscription"), field("event_type", "Event Type", "Select", options="Invoice\nPayment\nCredit\nAdjustment\nTop-Up\nRefund\nSubscription Activation", reqd=1),
		field("amount", "Amount", "Currency"), field("currency", "Currency", "Link", options="Currency"), field("status", "Status", "Select", options="Pending\nCompleted\nFailed\nCancelled", default="Pending"),
		field("provider", "Provider"), field("provider_reference", "Provider Reference"), field("period_start", "Period Start", "Date"), field("period_end", "Period End", "Date"),
		field("target_plan", "Target Plan", "Link", options="VerityAI Plan"), field("billing_cycle", "Billing Cycle", "Select", options="Monthly\nAnnual\nManual"),
		field("gateway_reference", "Gateway Reference"), field("gateway_status", "Gateway Status"), field("checkout_url", "Checkout URL", "Small Text"), field("poll_url", "Poll URL", "Small Text"),
		field("gateway_response_json", "Gateway Response", "Code", options="JSON"), field("usage_snapshot_json", "Usage Snapshot", "Code", options="JSON"), field("paid_on", "Paid On", "Datetime"),
	], "VBE-.#####")

	ensure_doctype("VerityAI Onboarding Checklist", [
		field("workspace", "Workspace", "Link", options="VerityAI Workspace", reqd=1, in_list_view=1), field("step_code", "Step Code", reqd=1, in_list_view=1),
		field("step_label", "Step Label", reqd=1), field("status", "Status", "Select", options="Not Started\nIn Progress\nDone\nSkipped", default="Not Started"),
		field("completed_on", "Completed On", "Datetime"), field("completed_by", "Completed By", "Link", options="User"),
	], "VOBC-.######")

	ensure_doctype("VerityAI Notification Setting", [
		field("workspace", "Workspace", "Link", options="VerityAI Workspace", reqd=1, unique=1, in_list_view=1), field("notification_email", "Notification Email", options="Email"),
		field("reply_to_email", "Reply-To Email", options="Email"), field("lead_notifications_enabled", "Lead Notifications Enabled", "Check", default=1),
		field("daily_summary_enabled", "Daily Summary Enabled", "Check"), field("human_handoff_alerts_enabled", "Human Handoff Alerts Enabled", "Check", default=1),
		field("quote_request_alerts_enabled", "Quote Request Alerts Enabled", "Check", default=1), field("usage_warning_alerts_enabled", "Usage Warning Alerts Enabled", "Check", default=1),
		field("provider_failure_alerts_enabled", "Provider Failure Alerts Enabled", "Check", default=1), field("alert_recipients", "Alert Recipients", "Small Text"),
		field("email_branding_name", "Email Branding Name"), field("email_footer", "Email Footer", "Small Text"), field("status", "Status", "Select", options="Active\nDisabled", default="Active"),
	], "VNS-.#####")

	ensure_doctype("VerityAI Email Delivery Log", [
		field("workspace", "Workspace", "Link", options="VerityAI Workspace", reqd=1, in_list_view=1), field("notification_type", "Notification Type", reqd=1),
		field("recipient", "Recipient", reqd=1), field("subject", "Subject", reqd=1), field("status", "Status", "Select", options="Pending\nSent\nFailed", default="Pending"),
		field("reference_doctype", "Reference DocType"), field("reference_name", "Reference Name"), field("error", "Error", "Small Text"), field("sent_on", "Sent On", "Datetime"),
	], "VEDL-.########")

	ensure_doctype("VerityAI WhatsApp Setup", [
		field("workspace", "Workspace", "Link", options="VerityAI Workspace", reqd=1, unique=1, in_list_view=1), field("mode", "Mode", "Select", options="Button Only\nLead Alerts\nFull AI Automation", default="Button Only"),
		field("business_whatsapp_number", "Business WhatsApp Number"), field("whatsapp_button_enabled", "WhatsApp Button Enabled", "Check", default=1),
		field("lead_alert_enabled", "Lead Alert Enabled", "Check"), field("full_ai_enabled", "Full AI Enabled", "Check"), field("setup_status", "Setup Status", "Select", options="Not Configured\nIn Progress\nConnected\nFailed", default="Not Configured"),
		field("meta_phone_number_id_status", "Meta Phone Number ID Status"), field("access_token_status", "Access Token Status"), field("webhook_status", "Webhook Status"),
		field("signature_verification_status", "Signature Verification Status"), field("last_tested_on", "Last Tested On", "Datetime"),
	], "VWA-.#####")

	ensure_doctype("VerityAI Integration Status", [
		field("workspace", "Workspace", "Link", options="VerityAI Workspace", reqd=1, in_list_view=1), field("integration_type", "Integration Type", "Select", options="Domain\nWidget\nWhatsApp\nEmail\nAI Provider\nERPNext", reqd=1),
		field("status", "Status", "Select", options="Not Configured\nConnected\nFailed\nWarning", default="Not Configured"), field("last_checked", "Last Checked", "Datetime"),
		field("details", "Details", "Small Text"), field("reference_doctype", "Reference DocType"), field("reference_name", "Reference Name"),
	], "VIS-.#####")


def ensure_default_plan():
	if frappe.db.exists("DocType", "VerityAI Plan") and not frappe.db.exists("VerityAI Plan", "TRIAL"):
		frappe.get_doc({
			"doctype": "VerityAI Plan", "plan_name": "Trial", "plan_code": "TRIAL", "active": 1,
			"currency": "USD", "trial_days": 14, "monthly_token_limit": 100000, "max_tokens": 900,
			"public_rate_limit_per_minute": 20, "max_public_message_chars": 4000,
			"max_team_members": 3, "max_knowledge_sources": 10, "max_allowed_domains": 2,
			"can_use_whatsapp_button": 1, "can_use_email_notifications": 1,
		}).insert(ignore_permissions=True)

