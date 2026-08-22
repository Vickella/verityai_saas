import json

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
	from verityai_saas.services.business_natures import seed_business_natures

	seed_business_natures()
	ensure_default_plan()
	ensure_workspace()
	from verityai_saas.services.platform_email import ensure_system_email_templates

	ensure_system_email_templates()
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


def workspace_link(label, link_to, parent_label):
	# ``parent_label`` is used by newer Frappe releases. Older releases group
	# links by their position after a Card Break and safely ignore this key.
	return {"label": label, "type": "Link", "link_type": "DocType", "link_to": link_to, "parent_label": parent_label}


def commerce_workspace_links():
	return [
		{"label": "Commerce", "type": "Card Break"},
		workspace_link("Customers", "VerityAI Customer", "Commerce"),
		workspace_link("Products", "VerityAI Product", "Commerce"),
		workspace_link("Product Prices", "VerityAI Product Price", "Commerce"),
		workspace_link("Quotations", "VerityAI Quotation", "Commerce"),
	]


def crm_workspace_links():
	return [
		workspace_link("Opportunities", "VerityAI Sales Opportunity", "Sales"),
		workspace_link("Appointments", "VerityAI Appointment", "Sales"),
		workspace_link("Activities", "VerityAI CRM Activity", "Sales"),
	]


def ensure_workspace():
	"""Add SaaS commerce and CRM links to the engine's existing Desk workspace."""
	name = "Verity AI"
	if not frappe.db.exists("Workspace", name):
		from verity_ai.setup_doctypes import ensure_workspace as ensure_engine_workspace

		ensure_engine_workspace()

	doc = frappe.get_doc("Workspace", name)
	doc.hide_custom = 1

	content = json.loads(doc.content or "[]")
	content = [row for row in content if row.get("data", {}).get("card_name") != "Commerce"]
	content.append({"type": "card", "data": {"card_name": "Commerce", "col": 3}})
	doc.content = json.dumps(content)

	crm_rows = crm_workspace_links()
	crm_targets = {row["link_to"] for row in crm_rows}
	links = []
	current_card = None
	for row in doc.links:
		if row.type == "Card Break":
			if current_card == "Sales":
				links.extend(crm_rows)
			current_card = row.label
		if current_card == "Commerce":
			continue
		# Tenant-specific engine settings are managed through the authenticated
		# platform integrations page, not exposed as a public Workspace link.
		if row.get("link_to") == "AI Configuration":
			continue
		if current_card == "Sales" and row.link_to in crm_targets:
			continue
		links.append(
			{
				"label": row.label,
				"type": row.type,
				"link_type": row.get("link_type"),
				"link_to": row.get("link_to"),
				"parent_label": row.get("parent_label"),
			}
		)
	if current_card == "Sales":
		links.extend(crm_rows)
	doc.set("links", links + commerce_workspace_links())
	doc.flags.ignore_version = True
	doc.save(ignore_permissions=True)


def permissions():
	full = {"read": 1, "write": 1, "create": 1, "delete": 1, "report": 1, "export": 1}
	return [{"role": "System Manager", **full}, {"role": ADMIN_ROLE, **full}, {"role": OPERATOR_ROLE, "read": 1, "report": 1, "export": 1}]


def platform_settings_permissions():
	full = {"read": 1, "write": 1, "create": 1}
	return [{"role": "System Manager", **full}, {"role": ADMIN_ROLE, **full}]


def field(fieldname, label, fieldtype="Data", **values):
	return {"fieldname": fieldname, "label": label, "fieldtype": fieldtype, **values}


def ensure_doctype(name, fields, autoname=None, istable=False, issingle=False, permission_rows=None):
	values = {
		"module": MODULE,
		"custom": 1,
		"istable": int(bool(istable)),
		"issingle": int(bool(issingle)),
		"track_changes": 1,
		"allow_import": int(not istable),
		"fields": [{**row, **({"default": str(row["default"])} if row.get("default") is not None else {})} for row in fields],
		"permissions": [] if istable else (permission_rows or permissions()),
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
		for key in ("module", "istable", "issingle", "track_changes", "allow_import", "autoname"):
			if key in values:
				setattr(doc, key, values[key])
		doc.flags.ignore_version = True
		doc.save(ignore_permissions=True)
		return
	frappe.get_doc({"doctype": "DocType", "name": name, **values}).insert(ignore_permissions=True)


def ensure_platform_settings():
	ensure_doctype(
		"VerityAI Platform Settings",
		[
			field("ai_section", "AI Provider", "Section Break"),
			field("ai_provider", "Provider", "Select", options="OpenAI\nOpenAI-Compatible", default="OpenAI"),
			field("ai_model", "Model", default="gpt-4.1-mini"),
			field("ai_api_base", "API Base URL"),
			field("ai_api_key", "API Key", "Password"),
			field("ai_embedding_model", "Embedding Model", default="text-embedding-3-small"),
			field("paynow_section", "Paynow", "Section Break"),
			field("paynow_environment", "Operating Mode", "Select", options="Test\nProduction", default="Test"),
			field("paynow_integration_id", "Integration ID"),
			field("paynow_integration_key", "Integration Key", "Password"),
		],
		issingle=True,
		permission_rows=platform_settings_permissions(),
	)


def ensure_doctypes():
	ensure_platform_settings()

	ensure_doctype("VerityAI Account", [
		field("account_name", "Account Name", reqd=1, unique=1, in_list_view=1),
		field("owner_user", "Owner User", "Link", options="User", reqd=1),
		field("billing_email", "Billing Email", options="Email", reqd=1), field("phone", "Phone"),
		field("country", "Country", "Link", options="Country"), field("currency", "Currency", "Link", options="Currency"),
		field("status", "Status", "Select", options="Active\nSuspended\nCancelled", default="Active", in_list_view=1),
		field("customer_type", "Customer Type", "Select", options="SME\nAgency\nEnterprise", default="SME"),
		field("referral_code", "Referral Code", unique=1), field("referred_by", "Referred By", "Link", options="VerityAI Account"),
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
			("can_manage_leads", "Can Manage Leads"), ("can_view_conversations", "Can View Conversations"), ("can_manage_conversations", "Can Manage Conversations"),
			("can_manage_billing", "Can Manage Billing"), ("can_manage_whatsapp", "Can Manage WhatsApp"),
			("can_manage_email", "Can Manage Email"), ("can_approve_quotes", "Can Approve Quotes"),
			("can_view_customers", "Can View Customers"), ("can_manage_customers", "Can Manage Customers"),
			("can_view_catalog", "Can View Catalogue"), ("can_manage_catalog", "Can Manage Catalogue"),
			("can_view_quotes", "Can View SaaS Quotes"), ("can_manage_quotes", "Can Manage SaaS Quotes"),
		)],
	], "hash")

	ensure_doctype("VerityAI Customer", [
		field("workspace", "Workspace", "Link", options="VerityAI Workspace", reqd=1, in_list_view=1, search_index=1),
		field("customer_name", "Customer Name", reqd=1, in_list_view=1, search_index=1),
		field("customer_type", "Customer Type", "Select", options="Company\nIndividual", default="Company"),
		field("email", "Email", options="Email", in_list_view=1, search_index=1), field("phone", "Phone", in_list_view=1),
		field("tax_id", "Tax ID"), field("address", "Address", "Small Text"), field("city", "City"),
		field("country", "Country", "Link", options="Country"), field("notes", "Notes", "Small Text"),
		field("status", "Status", "Select", options="Active\nDisabled", default="Active", in_list_view=1),
		field("external_system", "External System", "Select", options="\nERPNext"),
		field("external_id", "External ID"), field("last_synced_on", "Last Synced On", "Datetime", read_only=1),
		field("source_lead", "Source Lead", "Link", options="AI Lead", search_index=1), field("converted_on", "Converted On", "Datetime", read_only=1),
		field("lifetime_value", "Lifetime Value", "Currency", read_only=1), field("last_contact_on", "Last Contact On", "Datetime", read_only=1),
		field("next_follow_up_on", "Next Follow-up", "Datetime"),
	], "VCUST-.########")

	ensure_doctype("VerityAI Sales Opportunity", [
		field("workspace", "Workspace", "Link", options="VerityAI Workspace", reqd=1, in_list_view=1, search_index=1),
		field("opportunity_name", "Opportunity Name", reqd=1, in_list_view=1, search_index=1),
		field("lead", "Lead", "Link", options="AI Lead", search_index=1), field("customer", "Customer", "Link", options="VerityAI Customer", search_index=1),
		field("stage", "Stage", "Select", options="New\nQualified\nProposal\nNegotiation\nWon\nLost", default="New", reqd=1, in_list_view=1),
		field("amount", "Expected Value", "Currency", in_list_view=1), field("currency", "Currency", "Link", options="Currency", default="USD"),
		field("probability", "Probability %", "Percent", default=10), field("expected_close_date", "Expected Close Date", "Date", in_list_view=1),
		field("source", "Source"), field("assigned_to", "Assigned To", "Link", options="User", in_list_view=1),
		field("last_contact_on", "Last Contact On", "Datetime", read_only=1), field("next_follow_up_on", "Next Follow-up", "Datetime"),
		field("lost_reason", "Lost Reason", "Small Text"), field("notes", "Notes", "Text Editor"),
		field("external_system", "External System", "Select", options="\nERPNext"), field("external_id", "External ID"),
	], "VOPP-.########")

	ensure_doctype("VerityAI Appointment", [
		field("workspace", "Workspace", "Link", options="VerityAI Workspace", reqd=1, in_list_view=1, search_index=1),
		field("subject", "Subject", reqd=1, in_list_view=1), field("customer", "Customer", "Link", options="VerityAI Customer", search_index=1),
		field("lead", "Lead", "Link", options="AI Lead", search_index=1), field("opportunity", "Opportunity", "Link", options="VerityAI Sales Opportunity", search_index=1),
		field("starts_on", "Starts On", "Datetime", reqd=1, in_list_view=1), field("ends_on", "Ends On", "Datetime"), field("timezone", "Timezone"),
		field("mode", "Mode", "Select", options="Online\nPhone\nOnsite", default="Online"), field("location", "Location"), field("meeting_url", "Meeting URL"),
		field("assigned_to", "Assigned To", "Link", options="User", in_list_view=1),
		field("status", "Status", "Select", options="Scheduled\nConfirmed\nCompleted\nCancelled\nNo Show", default="Scheduled", in_list_view=1),
		field("notes", "Notes", "Small Text"), field("outcome", "Outcome", "Small Text"), field("reminder_sent", "Reminder Sent", "Check", read_only=1),
	], "VAPT-.########")

	ensure_doctype("VerityAI CRM Activity", [
		field("workspace", "Workspace", "Link", options="VerityAI Workspace", reqd=1, in_list_view=1, search_index=1),
		field("activity_type", "Activity Type", "Select", options="Call\nEmail\nMeeting\nNote\nFollow-up\nStatus Change", reqd=1, in_list_view=1),
		field("subject", "Subject", reqd=1, in_list_view=1), field("details", "Details", "Small Text"),
		field("lead", "Lead", "Link", options="AI Lead", search_index=1), field("customer", "Customer", "Link", options="VerityAI Customer", search_index=1),
		field("opportunity", "Opportunity", "Link", options="VerityAI Sales Opportunity", search_index=1), field("appointment", "Appointment", "Link", options="VerityAI Appointment"),
		field("scheduled_on", "Scheduled On", "Datetime"), field("completed_on", "Completed On", "Datetime", read_only=1),
		field("assigned_to", "Assigned To", "Link", options="User"), field("status", "Status", "Select", options="Open\nCompleted\nCancelled", default="Open", in_list_view=1),
	], "VCRM-.########")

	ensure_doctype("VerityAI Product", [
		field("workspace", "Workspace", "Link", options="VerityAI Workspace", reqd=1, in_list_view=1, search_index=1),
		field("item_code", "Item Code", reqd=1, in_list_view=1, search_index=1),
		field("item_name", "Item Name", reqd=1, in_list_view=1, search_index=1),
		field("description", "Description", "Text Editor"), field("item_group", "Item Group", default="Services"),
		field("stock_uom", "Unit of Measure", default="Unit"), field("is_stock_item", "Track Stock", "Check", default=0),
		field("standard_rate", "Standard Rate", "Currency"), field("currency", "Currency", "Link", options="Currency", default="USD"),
		field("active", "Active", "Check", default=1, in_list_view=1),
		field("external_system", "External System", "Select", options="\nERPNext"),
		field("external_id", "External ID"), field("last_synced_on", "Last Synced On", "Datetime", read_only=1),
	], "VPROD-.########")

	ensure_doctype("VerityAI Product Price", [
		field("workspace", "Workspace", "Link", options="VerityAI Workspace", reqd=1, in_list_view=1, search_index=1),
		field("product", "Product", "Link", options="VerityAI Product", reqd=1, in_list_view=1, search_index=1),
		field("price_list", "Price List", default="Standard Selling", reqd=1, in_list_view=1),
		field("currency", "Currency", "Link", options="Currency", default="USD", reqd=1),
		field("rate", "Rate", "Currency", reqd=1, in_list_view=1), field("valid_from", "Valid From", "Date"),
		field("valid_upto", "Valid Until", "Date"), field("active", "Active", "Check", default=1, in_list_view=1),
	], "VPRICE-.########")

	ensure_doctype("VerityAI Quotation Item", [
		field("product", "Product", "Link", options="VerityAI Product", reqd=1, in_list_view=1),
		field("item_code", "Item Code", reqd=1, in_list_view=1), field("item_name", "Item Name", reqd=1),
		field("description", "Description", "Small Text"), field("qty", "Quantity", "Float", reqd=1, default=1),
		field("uom", "Unit of Measure"), field("rate", "Rate", "Currency", reqd=1),
		field("discount_percent", "Discount %", "Percent", default=0), field("amount", "Amount", "Currency", read_only=1),
	], istable=True)

	ensure_doctype("VerityAI Quotation", [
		field("workspace", "Workspace", "Link", options="VerityAI Workspace", reqd=1, in_list_view=1, search_index=1),
		field("customer", "Customer", "Link", options="VerityAI Customer", reqd=1, in_list_view=1, search_index=1),
		field("customer_name", "Customer Name", read_only=1, in_list_view=1), field("customer_email", "Customer Email", options="Email", read_only=1),
		field("transaction_date", "Quotation Date", "Date", reqd=1, in_list_view=1), field("valid_till", "Valid Until", "Date"),
		field("price_list", "Price List", default="Standard Selling"), field("currency", "Currency", "Link", options="Currency", default="USD", reqd=1),
		field("status", "Status", "Select", options="Draft\nPending Approval\nApproved\nSent\nAccepted\nRejected\nExpired\nCancelled", default="Draft", in_list_view=1),
		field("items", "Items", "Table", options="VerityAI Quotation Item", reqd=1),
		field("subtotal", "Subtotal", "Currency", read_only=1), field("discount_amount", "Additional Discount", "Currency", default=0),
		field("tax_rate", "Tax Rate %", "Percent", default=0), field("tax_amount", "Tax Amount", "Currency", read_only=1),
		field("total", "Total", "Currency", read_only=1, in_list_view=1), field("notes", "Terms and Notes", "Text Editor"),
		field("external_system", "External System", "Select", options="\nERPNext"), field("external_id", "External ID"),
		field("sync_status", "Sync Status", "Select", options="Not Synced\nPending\nSynced\nFailed", default="Not Synced"),
		field("sync_error", "Sync Error", "Small Text", read_only=1), field("last_synced_on", "Last Synced On", "Datetime", read_only=1),
	], "VQUOTE-.########")

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
		field("period_start", "Period Start", "Date"), field("period_end", "Period End", "Date"), field("opening_token_allowance", "Plan AI Credits", "Int"),
		field("top_up_tokens", "Purchased AI Credits", "Int"), field("promotional_credits", "Promotional AI Credits", "Int"),
		field("promotional_credits_expire_on", "Promotional Credits Expire On", "Date"),
		field("tokens_used", "AI Credits Used", "Int"), field("tokens_remaining", "AI Credits Remaining", "Int"),
		field("web_conversations_used", "Web Conversations Used", "Int"), field("whatsapp_messages_used", "WhatsApp Messages Used", "Int"), field("email_sends_used", "Email Sends Used", "Int"),
		field("estimated_ai_cost", "Estimated AI Cost", "Currency"), field("estimated_revenue", "Estimated Revenue", "Currency"), field("estimated_gross_margin", "Estimated Gross Margin", "Currency"),
		field("status", "Status", "Select", options="Normal\nWarning\nExhausted\nSuspended", default="Normal"), field("last_synced_from_usage_logs", "Last Synced From Usage Logs", "Datetime"),
	], "VWAL-.#####")

	ensure_doctype("VerityAI Usage Transaction", [
		field("workspace", "Workspace", "Link", options="VerityAI Workspace", reqd=1, in_list_view=1), field("engine_tenant", "Engine Tenant", "Link", options="AI Tenant", reqd=1),
		field("ai_usage_log", "AI Usage Log", "Link", options="AI Usage Log", unique=1), field("transaction_type", "Transaction Type", "Select", options="Usage\nBlocked\nTop-Up\nCredit\nAdjustment\nRefund", reqd=1),
		field("platform", "Platform"), field("input_tokens", "Input Tokens", "Int"), field("output_tokens", "Output Tokens", "Int"), field("total_tokens", "Total Tokens", "Int"),
		field("estimated_cost", "Estimated Cost", "Currency"), field("billable_amount", "Billable Amount", "Currency"), field("period", "Period"),
	], "VUTX-.########")

	ensure_doctype("VerityAI Billing Event", [
		field("account", "Account", "Link", options="VerityAI Account", reqd=1), field("workspace", "Workspace", "Link", options="VerityAI Workspace", reqd=1, in_list_view=1),
		field("subscription", "Subscription", "Link", options="VerityAI Subscription"), field("event_type", "Event Type", "Select", options="Invoice\nPayment\nCredit\nAdjustment\nTop-Up\nRefund\nSubscription Activation", reqd=1),
		field("amount", "Amount", "Currency"), field("currency", "Currency", "Link", options="Currency"), field("status", "Status", "Select", options="Pending\nCompleted\nFailed\nCancelled", default="Pending"),
		field("provider", "Provider"), field("provider_reference", "Provider Reference"), field("period_start", "Period Start", "Date"), field("period_end", "Period End", "Date"),
		field("transaction_kind", "Transaction Kind", "Select", options="Subscription\nCredit Top-Up", default="Subscription"),
		field("target_plan", "Target Plan", "Link", options="VerityAI Plan"), field("credit_pack", "Credit Pack", "Link", options="VerityAI Credit Pack"),
		field("purchased_credits", "Purchased AI Credits", "Int"), field("gross_amount", "Gross Amount", "Currency"),
		field("discount_amount", "Discount Amount", "Currency"), field("promotion", "Promotion", "Link", options="VerityAI Promotion"),
		field("billing_cycle", "Billing Cycle", "Select", options="Monthly\nAnnual\nManual"),
		field("gateway_reference", "Gateway Reference"), field("gateway_status", "Gateway Status"), field("checkout_url", "Checkout URL", "Small Text"), field("poll_url", "Poll URL", "Small Text"),
		field("live_checkout_verified", "Live Checkout Verified", "Check", default=0),
		field("gateway_response_json", "Gateway Response", "Code", options="JSON"), field("usage_snapshot_json", "Usage Snapshot", "Code", options="JSON"), field("paid_on", "Paid On", "Datetime"),
	], "VBE-.#####")

	ensure_doctype("VerityAI Credit Pack", [
		field("pack_name", "Pack Name", reqd=1, unique=1, in_list_view=1), field("pack_code", "Pack Code", reqd=1, unique=1, in_list_view=1),
		field("active", "Active", "Check", default=1, in_list_view=1), field("credits", "AI Credits", "Int", reqd=1, in_list_view=1),
		field("price", "Price", "Currency", reqd=1, in_list_view=1), field("currency", "Currency", "Link", options="Currency", default="USD"),
		field("sort_order", "Sort Order", "Int", default=10),
	], "field:pack_code")

	ensure_doctype("VerityAI Promotion", [
		field("promotion_name", "Promotion Name", reqd=1, in_list_view=1), field("code", "Code", reqd=1, unique=1, in_list_view=1),
		field("active", "Active", "Check", default=1, in_list_view=1), field("discount_percent", "Discount Percent", "Percent"),
		field("bonus_credits", "Bonus AI Credits", "Int"), field("valid_from", "Valid From", "Date"), field("valid_until", "Valid Until", "Date"),
		field("max_redemptions", "Maximum Redemptions", "Int"), field("per_account_limit", "Per Account Limit", "Int", default=1),
		field("minimum_plan", "Minimum Plan", "Link", options="VerityAI Plan"), field("notes", "Notes", "Small Text"),
	], "VPROMO-.#####")

	ensure_doctype("VerityAI Promotion Redemption", [
		field("promotion", "Promotion", "Link", options="VerityAI Promotion", reqd=1, in_list_view=1),
		field("account", "Account", "Link", options="VerityAI Account", reqd=1), field("workspace", "Workspace", "Link", options="VerityAI Workspace", reqd=1, in_list_view=1),
		field("billing_event", "Billing Event", "Link", options="VerityAI Billing Event", reqd=1), field("status", "Status", "Select", options="Reserved\nGranted\nReversed", default="Reserved", in_list_view=1),
		field("discount_amount", "Discount Amount", "Currency"), field("bonus_credits", "Bonus AI Credits", "Int"), field("redeemed_on", "Redeemed On", "Datetime"),
	], "VPR-.########")

	ensure_doctype("VerityAI Referral Reward", [
		field("referrer_account", "Referrer Account", "Link", options="VerityAI Account", reqd=1, in_list_view=1),
		field("referrer_workspace", "Referrer Workspace", "Link", options="VerityAI Workspace", reqd=1),
		field("referred_account", "Referred Account", "Link", options="VerityAI Account", reqd=1),
		field("referred_workspace", "Referred Workspace", "Link", options="VerityAI Workspace", reqd=1, in_list_view=1),
		field("billing_event", "Qualifying Billing Event", "Link", options="VerityAI Billing Event", reqd=1, unique=1),
		field("reward_credits", "Reward AI Credits", "Int", default=50000),
		field("status", "Status", "Select", options="Pending\nGranted\nReversed\nRejected", default="Pending", in_list_view=1),
		field("eligible_on", "Eligible On", "Date"), field("granted_on", "Granted On", "Datetime"), field("expires_on", "Expires On", "Date"),
		field("review_note", "Review Note", "Small Text"),
	], "VRR-.########")

	ensure_doctype("VerityAI Report Schedule", [
		field("report_name", "Report Name", reqd=1, in_list_view=1), field("report_type", "Report Type", "Select", options="Operator Summary\nWorkspace Analytics", reqd=1, in_list_view=1),
		field("workspace", "Workspace", "Link", options="VerityAI Workspace"), field("recipients", "Recipients", "Small Text", reqd=1), field("frequency", "Frequency", "Select", options="Daily\nWeekly\nMonthly", default="Weekly", in_list_view=1),
		field("active", "Active", "Check", default=1, in_list_view=1), field("last_sent_on", "Last Sent On", "Datetime"), field("next_send_on", "Next Send On", "Datetime"), field("last_status", "Last Status"), field("last_error", "Last Error", "Small Text"),
	], "VRS-.########")
	ensure_doctype("VerityAI Knowledge Ingestion", [
		field("workspace", "Workspace", "Link", options="VerityAI Workspace", reqd=1, in_list_view=1), field("knowledge_source", "Knowledge Source", "Link", options="AI Knowledge Source"),
		field("title", "Title", reqd=1, in_list_view=1), field("source_type", "Source Type", "Select", options="Text\nFile\nURL", reqd=1, in_list_view=1),
		field("source_url", "Source URL", "Small Text"), field("file_url", "File URL", "Data"), field("status", "Status", "Select", options="Pending\nProcessing\nReady\nFailed", default="Pending", in_list_view=1),
		field("content_hash", "Content Hash"), field("pages_processed", "Pages Processed", "Int"), field("bytes_processed", "Bytes Processed", "Int"),
		field("last_refreshed_on", "Last Refreshed On", "Datetime"), field("next_refresh_on", "Next Refresh On", "Datetime"), field("error", "Error", "Small Text"),
	], "VKI-.########")
	ensure_doctype("VerityAI Lead Activity", [
		field("workspace", "Workspace", "Link", options="VerityAI Workspace", reqd=1, in_list_view=1), field("lead", "Lead", "Link", options="AI Lead", reqd=1, in_list_view=1),
		field("activity_type", "Activity Type", "Select", options="Note\nAssignment\nStatus Change", reqd=1, in_list_view=1), field("note", "Note", "Small Text"),
		field("assigned_to", "Assigned To", "Link", options="User"), field("old_status", "Old Status"), field("new_status", "New Status"), field("performed_by", "Performed By", "Link", options="User"),
	], "VLA-.########")

	ensure_doctype("VerityAI Conversation Handoff", [
		field("workspace", "Workspace", "Link", options="VerityAI Workspace", reqd=1, in_list_view=1), field("conversation", "Conversation", "Link", options="AI Chat Session", reqd=1, unique=1, in_list_view=1),
		field("status", "Status", "Select", options="Open\nAssigned\nResolved", default="Open", in_list_view=1), field("assigned_to", "Assigned To", "Link", options="User", in_list_view=1),
		field("opened_on", "Opened On", "Datetime"), field("resolved_on", "Resolved On", "Datetime"), field("resolved_by", "Resolved By", "Link", options="User"), field("history_json", "History", "Code", options="JSON"),
	], "VHO-.########")
	ensure_doctype("VerityAI Billing Document", [
		field("workspace", "Workspace", "Link", options="VerityAI Workspace", reqd=1, in_list_view=1), field("account", "Account", "Link", options="VerityAI Account", reqd=1),
		field("subscription", "Subscription", "Link", options="VerityAI Subscription"), field("billing_event", "Billing Event", "Link", options="VerityAI Billing Event", reqd=1),
		field("document_type", "Document Type", "Select", options="Invoice\nReceipt\nCredit Note\nRefund Confirmation", reqd=1, in_list_view=1),
		field("document_number", "Document Number", reqd=1, unique=1, in_list_view=1), field("status", "Status", "Select", options="Draft\nIssued\nPaid\nCancelled", default="Issued", in_list_view=1),
		field("issue_date", "Issue Date", "Date"), field("due_date", "Due Date", "Date"), field("paid_on", "Paid On", "Datetime"),
		field("currency", "Currency", "Link", options="Currency"), field("subtotal", "Subtotal", "Currency"), field("tax_amount", "Tax Amount", "Currency"), field("total", "Total", "Currency"),
		field("provider_reference", "Provider Reference"), field("rendered_html", "Rendered HTML", "Code", options="HTML"), field("checksum", "Checksum", unique=1),
	], "VBILL-.########")
	ensure_doctype("VerityAI Onboarding Checklist", [
		field("workspace", "Workspace", "Link", options="VerityAI Workspace", reqd=1, in_list_view=1), field("step_code", "Step Code", reqd=1, in_list_view=1),
		field("step_label", "Step Label", reqd=1), field("status", "Status", "Select", options="Not Started\nIn Progress\nDone\nSkipped", default="Not Started"),
		field("completed_on", "Completed On", "Datetime"), field("completed_by", "Completed By", "Link", options="User"),
	], "VOBC-.######")

	ensure_doctype("VerityAI API Credential", [
		field("workspace", "Workspace", "Link", options="VerityAI Workspace", reqd=1, in_list_view=1),
		field("label", "Label", reqd=1, in_list_view=1), field("token_prefix", "Token Prefix", read_only=1, in_list_view=1),
		field("token_hash", "Token Hash", read_only=1, reqd=1, unique=1), field("scopes", "Scopes", "Small Text", reqd=1),
		field("active", "Active", "Check", default=1, in_list_view=1), field("last_used_on", "Last Used On", "Datetime", read_only=1),
	], "VAPI-.########")

	ensure_doctype("VerityAI Notification Setting", [
		field("workspace", "Workspace", "Link", options="VerityAI Workspace", reqd=1, unique=1, in_list_view=1), field("notification_email", "Notification Email", options="Email"),
		field("reply_to_email", "Reply-To Email", options="Email"), field("lead_notifications_enabled", "Lead Notifications Enabled", "Check", default=1),
		field("daily_summary_enabled", "Daily Summary Enabled", "Check"), field("human_handoff_alerts_enabled", "Human Handoff Alerts Enabled", "Check", default=1),
		field("quote_request_alerts_enabled", "Quote Request Alerts Enabled", "Check", default=1), field("usage_warning_alerts_enabled", "Usage Warning Alerts Enabled", "Check", default=1),
		field("provider_failure_alerts_enabled", "Provider Failure Alerts Enabled", "Check", default=1), field("alert_recipients", "Alert Recipients", "Small Text"),
		field("email_branding_name", "Email Branding Name"), field("email_footer", "Email Footer", "Small Text"), field("status", "Status", "Select", options="Active\nDisabled", default="Active"),
		field("custom_smtp_enabled", "Use Custom SMTP", "Check"), field("smtp_host", "SMTP Host"), field("smtp_port", "SMTP Port", "Int", default=587),
		field("smtp_use_tls", "Use STARTTLS", "Check", default=1), field("smtp_username", "SMTP Username"), field("smtp_password", "SMTP Password", "Password"), field("smtp_sender_email", "SMTP Sender Email", options="Email"),
	], "VNS-.#####")

	ensure_doctype("VerityAI Email Delivery Log", [
		field("workspace", "Workspace", "Link", options="VerityAI Workspace", reqd=1, in_list_view=1), field("notification_type", "Notification Type", reqd=1),
		field("recipient", "Recipient", reqd=1), field("subject", "Subject", reqd=1), field("status", "Status", "Select", options="Pending\nSent\nFailed", default="Pending"),
		field("reference_doctype", "Reference DocType"), field("reference_name", "Reference Name"), field("message", "Message", "Code", options="HTML"), field("error", "Error", "Small Text"), field("sent_on", "Sent On", "Datetime"),
	], "VEDL-.########")

	ensure_doctype("VerityAI WhatsApp Setup", [
		field("workspace", "Workspace", "Link", options="VerityAI Workspace", reqd=1, unique=1, in_list_view=1), field("mode", "Mode", "Select", options="Button Only\nLead Alerts\nFull AI Automation", default="Button Only"),
		field("business_whatsapp_number", "Business WhatsApp Number"), field("whatsapp_button_enabled", "WhatsApp Button Enabled", "Check", default=1),
		field("lead_alert_enabled", "Lead Alert Enabled", "Check"), field("full_ai_enabled", "Full AI Enabled", "Check"), field("setup_status", "Setup Status", "Select", options="Not Configured\nIn Progress\nConnected\nFailed", default="Not Configured"),
		field("meta_phone_number_id_status", "Meta Phone Number ID Status"), field("access_token_status", "Access Token Status"), field("webhook_status", "Webhook Status"),
		field("signature_verification_status", "Signature Verification Status"), field("last_tested_on", "Last Tested On", "Datetime"), field("last_webhook_on", "Last Webhook On", "Datetime"), field("last_webhook_event", "Last Webhook Event"),
	], "VWA-.#####")

	ensure_doctype("VerityAI Integration Status", [
		field("workspace", "Workspace", "Link", options="VerityAI Workspace", reqd=1, in_list_view=1), field("integration_type", "Integration Type", "Select", options="Domain\nWidget\nWhatsApp\nEmail\nAI Provider\nERPNext", reqd=1),
		field("status", "Status", "Select", options="Not Configured\nConnected\nFailed\nWarning", default="Not Configured"), field("last_checked", "Last Checked", "Datetime"),
		field("details", "Details", "Small Text"), field("reference_doctype", "Reference DocType"), field("reference_name", "Reference Name"),
	], "VIS-.#####")

	ensure_doctype("VerityAI Credit Stock Ledger", [
		field("posting_datetime", "Posting Date and Time", "Datetime", reqd=1, in_list_view=1),
		field("entry_type", "Entry Type", "Select", options="Opening Balance\nPurchase\nAllocation\nReversal\nAdjustment", reqd=1, in_list_view=1),
		field("direction", "Direction", "Select", options="Receipt\nIssue", reqd=1),
		field("credits", "AI Credits", "Int", reqd=1, in_list_view=1),
		field("unit_cost", "Unit Cost", "Currency", read_only=1),
		field("inventory_value", "Inventory Value", "Currency", read_only=1),
		field("revenue", "Revenue", "Currency", read_only=1),
		field("cogs", "Cost of Sales", "Currency", read_only=1),
		field("gross_profit", "Gross Profit", "Currency", read_only=1),
		field("balance_credits", "Credit Balance", "Int", read_only=1, in_list_view=1),
		field("balance_value", "Stock Value", "Currency", read_only=1),
		field("currency", "Currency", "Link", options="Currency", default="USD", reqd=1),
		field("workspace", "Workspace", "Link", options="VerityAI Workspace"),
		field("billing_event", "Billing Event", "Link", options="VerityAI Billing Event"),
		field("source_key", "Source Key", unique=1, read_only=1),
		field("reference", "Reference"), field("notes", "Notes", "Small Text"),
		field("erpnext_status", "ERPNext Status", "Select", options="Not Applicable\nPending\nPosted\nFailed", default="Not Applicable", read_only=1),
		field("erpnext_journal_entry", "ERPNext Journal Entry", read_only=1),
		field("erpnext_error", "ERPNext Error", "Small Text", read_only=1),
	], "VCSTK-.########", permission_rows=platform_settings_permissions())

	ensure_doctype("VerityAI ERPNext Accounting Settings", [
		field("enabled", "Enabled", "Check"), field("auto_post", "Post Automatically", "Check"),
		field("erpnext_url", "ERPNext URL"), field("api_key", "API Key", "Password"), field("api_secret", "API Secret", "Password"),
		field("company", "Company"), field("currency", "Currency", "Link", options="Currency", default="USD"),
		field("receivable_account", "Bank or Receivable Account"), field("sales_account", "Sales Account"),
		field("inventory_account", "AI Credit Inventory Account"), field("cogs_account", "Cost of Sales Account"),
		field("cost_center", "Cost Center"),
		field("connection_status", "Connection Status", "Select", options="Not Configured\nNot Checked\nConnected\nFailed", default="Not Configured", read_only=1),
		field("last_checked_on", "Last Checked On", "Datetime", read_only=1), field("last_error", "Last Error", "Small Text", read_only=1),
	], issingle=True, permission_rows=platform_settings_permissions())

	ensure_doctype("VerityAI ERPNext Connection", [
		field("workspace", "Workspace", "Link", options="VerityAI Workspace", reqd=1, unique=1, in_list_view=1),
		field("enabled", "Enabled", "Check"), field("erpnext_url", "ERPNext URL", reqd=1),
		field("api_key", "API Key", "Password"), field("api_secret", "API Secret", "Password"),
		field("company", "Company"), field("selling_price_list", "Selling Price List", default="Standard Selling"),
		field("customer_group", "Customer Group", default="All Customer Groups"),
		field("territory", "Territory", default="All Territories"),
		field("sales_taxes_template", "Sales Taxes and Charges Template"),
		field("auto_sync_quotations", "Sync Approved Quotations", "Check", default=1),
		field("assistant_connector_enabled", "Use VerityAI ERPNext Connector", "Check"),
		field("connection_status", "Connection Status", "Select", options="Not Configured\nNot Checked\nConnected\nFailed", default="Not Configured", read_only=1),
		field("last_checked_on", "Last Checked On", "Datetime", read_only=1),
		field("last_product_sync_on", "Last Product Sync On", "Datetime", read_only=1),
		field("last_error", "Last Error", "Small Text", read_only=1),
	], "VERPC-.#####")


def ensure_default_plan():
	if not frappe.db.exists("DocType", "VerityAI Plan"):
		return
	plans = (
		{"plan_name": "Trial", "plan_code": "TRIAL", "monthly_price": 0, "annual_price": 0, "trial_days": 7,
		 "monthly_token_limit": 5000, "max_tokens": 400, "max_workspaces": 1, "max_assistants": 1, "max_team_members": 1,
		 "monthly_web_conversations": 5, "monthly_whatsapp_messages": 0, "monthly_email_sends": 25,
		 "max_knowledge_sources": 3, "max_allowed_domains": 1, "public_rate_limit_per_minute": 10,
		 "max_public_message_chars": 2000, "can_use_whatsapp_button": 1, "can_use_email_notifications": 1, "support_level": "Community"},
		{"plan_name": "Launch", "plan_code": "LAUNCH", "monthly_price": 5, "annual_price": 50, "trial_days": 0,
		 "monthly_token_limit": 100000, "max_tokens": 700, "max_workspaces": 1, "max_assistants": 1, "max_team_members": 1,
		 "monthly_web_conversations": 50, "monthly_whatsapp_messages": 0, "monthly_email_sends": 250,
		 "max_knowledge_sources": 5, "max_allowed_domains": 1, "public_rate_limit_per_minute": 30,
		 "max_public_message_chars": 4000, "can_use_whatsapp_button": 1, "can_use_email_notifications": 1,
		 "can_use_quotation_workflow": 1, "support_level": "Community"},
		{"plan_name": "Growth", "plan_code": "GROWTH", "monthly_price": 12, "annual_price": 120, "trial_days": 0,
		 "monthly_token_limit": 400000, "max_tokens": 1000, "max_workspaces": 1, "max_assistants": 1, "max_team_members": 3,
		 "monthly_web_conversations": 200, "monthly_whatsapp_messages": 100, "monthly_email_sends": 1500,
		 "max_knowledge_sources": 20, "max_allowed_domains": 3, "public_rate_limit_per_minute": 60,
		 "max_public_message_chars": 6000, "can_remove_branding": 1, "can_use_whatsapp_button": 1, "can_use_whatsapp_ai": 1,
		 "can_use_email_notifications": 1, "can_use_custom_smtp": 1, "can_use_quotation_workflow": 1, "support_level": "Standard"},
		{"plan_name": "Scale", "plan_code": "SCALE", "monthly_price": 20, "annual_price": 200, "trial_days": 0,
		 "monthly_token_limit": 1000000, "max_tokens": 1400, "max_workspaces": 3, "max_assistants": 3, "max_team_members": 5,
		 "monthly_web_conversations": 500, "monthly_whatsapp_messages": 300, "monthly_email_sends": 5000,
		 "max_knowledge_sources": 60, "max_allowed_domains": 10, "public_rate_limit_per_minute": 120,
		 "max_public_message_chars": 8000, "can_remove_branding": 1, "can_use_whatsapp_button": 1, "can_use_whatsapp_ai": 1,
		 "can_use_email_notifications": 1, "can_use_custom_smtp": 1, "can_use_erpnext_integration": 1,
		 "can_use_quotation_workflow": 1, "can_use_api_access": 1, "can_bring_own_ai_provider_key": 1, "support_level": "Priority"},
		{"plan_name": "Enterprise", "plan_code": "ENTERPRISE", "active": 0, "monthly_price": 100, "annual_price": 1000, "trial_days": 0,
		 "monthly_token_limit": 12000000, "max_tokens": 1800, "max_workspaces": 5, "max_assistants": 5, "max_team_members": 30,
		 "monthly_web_conversations": 7500, "monthly_whatsapp_messages": 4000, "monthly_email_sends": 50000,
		 "max_knowledge_sources": 500, "max_allowed_domains": 50, "public_rate_limit_per_minute": 240,
		 "max_public_message_chars": 10000, "can_remove_branding": 1, "can_use_whatsapp_button": 1, "can_use_whatsapp_ai": 1,
		 "can_use_email_notifications": 1, "can_use_custom_smtp": 1, "can_use_erpnext_integration": 1,
		 "can_use_quotation_workflow": 1, "can_use_api_access": 1, "can_bring_own_ai_provider_key": 1, "support_level": "Priority"},
	)
	for values in plans:
		name = frappe.db.get_value("VerityAI Plan", {"plan_code": values["plan_code"]}, "name")
		doc = frappe.get_doc("VerityAI Plan", name) if name else frappe.get_doc({"doctype": "VerityAI Plan"})
		doc.update({"active": 1, "currency": "USD", **values})
		doc.save(ignore_permissions=True) if name else doc.insert(ignore_permissions=True)

	if frappe.db.exists("DocType", "VerityAI Credit Pack"):
		current_pack_codes = {"CREDITS-200K", "CREDITS-500K", "CREDITS-1_2M"}
		for old_pack in frappe.get_all("VerityAI Credit Pack", fields=["name", "pack_code"]):
			if old_pack.pack_code not in current_pack_codes:
				frappe.db.set_value("VerityAI Credit Pack", old_pack.name, "active", 0)
		for values in (
			{"pack_name": "200,000 AI Credits", "pack_code": "CREDITS-200K", "credits": 200000, "price": 5, "sort_order": 10},
			{"pack_name": "500,000 AI Credits", "pack_code": "CREDITS-500K", "credits": 500000, "price": 10, "sort_order": 20},
			{"pack_name": "1,200,000 AI Credits", "pack_code": "CREDITS-1_2M", "credits": 1200000, "price": 20, "sort_order": 30},
		):
			name = frappe.db.get_value("VerityAI Credit Pack", {"pack_code": values["pack_code"]}, "name")
			doc = frappe.get_doc("VerityAI Credit Pack", name) if name else frappe.get_doc({"doctype": "VerityAI Credit Pack"})
			doc.update({"active": 1, "currency": "USD", **values})
			doc.save(ignore_permissions=True) if name else doc.insert(ignore_permissions=True)
