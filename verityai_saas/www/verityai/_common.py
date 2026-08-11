import frappe
from frappe.sessions import get_csrf_token

from verityai_saas import __version__


PAGE_META = {
	"dashboard": ("Dashboard", "A clear view of setup, activity, plan health and capacity."),
	"health": ("Health", "Monitor workspace services, integrations and operational alerts."),
	"onboarding": ("Setup", "Complete the essentials required to launch your AI assistant."),
	"assistant": ("Assistant", "Define the assistant identity and industry-specific sales discovery."),
	"widget": ("Widget", "Style and deploy the assistant on approved websites."),
	"knowledge": ("Knowledge", "Manage the trusted content your assistant can use in conversations."),
	"leads": ("Leads", "Qualify, assign and progress every captured prospect."),
	"crm": ("Sales CRM", "Manage opportunities, appointments and follow-up activity."),
	"conversations": ("Conversations", "Review customer interactions and coordinate human handoff."),
	"commerce": ("Commerce", "Manage customers, products and quotations."),
	"quotes": ("AI Quote Requests", "Review and approve quotations prepared by the assistant."),
	"usage": ("Usage", "Understand token consumption, activity and account capacity."),
	"billing": ("Billing", "Review your subscription, invoices and payment activity."),
	"email": ("Email", "Control workspace notifications and delivery preferences."),
	"whatsapp": ("WhatsApp", "Connect and monitor the workspace messaging channel."),
	"team": ("Team", "Invite colleagues and apply least-privilege workspace access."),
	"account": ("Account", "Maintain business details and isolated workspaces."),
}


def portal_context(context, page):
	if frappe.session.user == "Guest":
		frappe.local.flags.redirect_location = "/login?redirect-to=/verityai"
		raise frappe.Redirect
	context.no_cache = 1
	page_title, page_description = PAGE_META.get(page, (page.replace("_", " ").title(), ""))
	context.title = f"VerityAI · {page_title}"
	context.portal_page = page
	context.page_title = page_title
	context.page_description = page_description
	context.user_email = frappe.session.user
	context.csrf_token = get_csrf_token()
	context.asset_version = __version__
	return context
