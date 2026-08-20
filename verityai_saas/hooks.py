app_name = "verityai_saas"
app_title = "VerityAI SaaS"
app_publisher = "VerityCore Consultancy (Pvt) Ltd"
app_description = "Customer SaaS layer for Verity AI"
app_email = "devs@veritycore.co.zw"
app_license = "mit"

before_install = "verityai_saas.install.validate_engine_installation"
after_install = "verityai_saas.setup_doctypes.install"
web_include_css = "/assets/verityai_saas/css/portal.css"
web_include_js = "/assets/verityai_saas/js/portal.js"
home_page = "verityai"

permission_query_conditions = {
	"VerityAI Account": "verityai_saas.services.permissions.account_query_condition",
	"VerityAI Workspace": "verityai_saas.services.permissions.workspace_query_condition",
	"VerityAI Workspace Member": "verityai_saas.services.permissions.member_query_condition",
	"VerityAI Subscription": "verityai_saas.services.permissions.workspace_child_query_condition",
	"VerityAI Usage Wallet": "verityai_saas.services.permissions.workspace_child_query_condition",
	"VerityAI Usage Transaction": "verityai_saas.services.permissions.workspace_child_query_condition",
	"VerityAI Billing Event": "verityai_saas.services.permissions.workspace_child_query_condition",
	"VerityAI Billing Document": "verityai_saas.services.permissions.workspace_child_query_condition",
	"VerityAI API Credential": "verityai_saas.services.permissions.workspace_child_query_condition",
	"VerityAI Lead Activity": "verityai_saas.services.permissions.workspace_child_query_condition",
	"VerityAI Knowledge Ingestion": "verityai_saas.services.permissions.workspace_child_query_condition",
	"VerityAI Conversation Handoff": "verityai_saas.services.permissions.workspace_child_query_condition",
	"VerityAI Onboarding Checklist": "verityai_saas.services.permissions.workspace_child_query_condition",
	"VerityAI Notification Setting": "verityai_saas.services.permissions.workspace_child_query_condition",
	"VerityAI Email Delivery Log": "verityai_saas.services.permissions.workspace_child_query_condition",
	"VerityAI WhatsApp Setup": "verityai_saas.services.permissions.workspace_child_query_condition",
	"VerityAI Integration Status": "verityai_saas.services.permissions.workspace_child_query_condition",
	"VerityAI ERPNext Connection": "verityai_saas.services.permissions.workspace_child_query_condition",
	"VerityAI Customer": "verityai_saas.services.permissions.workspace_child_query_condition",
	"VerityAI Product": "verityai_saas.services.permissions.workspace_child_query_condition",
	"VerityAI Product Price": "verityai_saas.services.permissions.workspace_child_query_condition",
	"VerityAI Quotation": "verityai_saas.services.permissions.workspace_child_query_condition",
	"VerityAI Sales Opportunity": "verityai_saas.services.permissions.workspace_child_query_condition",
	"VerityAI Appointment": "verityai_saas.services.permissions.workspace_child_query_condition",
	"VerityAI CRM Activity": "verityai_saas.services.permissions.workspace_child_query_condition",
	"VerityAI Promotion Redemption": "verityai_saas.services.permissions.workspace_child_query_condition",
}

role_home_page = {
	"VerityAI Customer Owner": "verityai",
	"VerityAI Customer Admin": "verityai",
	"VerityAI Sales User": "verityai",
	"VerityAI Support User": "verityai",
	"VerityAI Billing User": "verityai",
	"VerityAI Viewer": "verityai",
}
scheduler_events = {
	"hourly": ["verityai_saas.services.usage.sync_all_usage", "verityai_saas.services.billing.check_subscription_expiry"],
	"daily": ["verityai_saas.services.notifications.send_daily_summaries", "verityai_saas.services.platform_email.send_trial_lifecycle_emails", "verityai_saas.services.billing.check_trial_expiry", "verityai_saas.services.billing.roll_usage_periods", "verityai_saas.services.billing.send_payment_reminders", "verityai_saas.services.analytics.send_due_reports", "verityai_saas.services.notifications.send_usage_warnings", "verityai_saas.services.commercial.process_referral_rewards"],
}

doc_events = {
	"AI Lead": {"after_insert": "verityai_saas.services.notifications.send_lead_notification"},
	"AI Chat Session": {
		"after_insert": "verityai_saas.services.whatsapp.record_channel_activity",
		"on_update": "verityai_saas.services.notifications.send_handoff_notification",
	},
	"AI Quotation Request": {"after_insert": "verityai_saas.services.notifications.send_quote_request_notification"},
	"AI Monitoring Alert": {"after_insert": "verityai_saas.services.notifications.send_provider_failure_notification"},
}

verity_ai_entitlement_check = ["verityai_saas.services.entitlements.check_engine_request"]
verity_ai_item_price_handler = ["verityai_saas.services.commerce.handle_ai_item_price"]
verity_ai_quotation_request_handler = ["verityai_saas.services.commerce.handle_ai_quotation_request"]
verity_ai_quote_status_handler = ["verityai_saas.services.commerce.handle_ai_quote_status"]
verity_ai_commerce_capability_handler = ["verityai_saas.services.commerce.handle_ai_commerce_capabilities"]
verity_ai_catalog_search_handler = ["verityai_saas.services.commerce.handle_ai_catalog_search"]
verity_ai_lead_capture_handler = ["verityai_saas.services.commerce.handle_ai_lead_capture"]
verity_ai_sales_crm_handler = ["verityai_saas.services.commerce.handle_ai_sales_crm"]
