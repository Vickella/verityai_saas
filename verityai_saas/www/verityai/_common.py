import frappe
from frappe.sessions import get_csrf_token

from verityai_saas import __version__


PAGE_META = {
	"dashboard": ("Dashboard", "Overview"),
	"health": ("Health", "Services and alerts"),
	"onboarding": ("Setup", "Launch progress"),
	"assistant": ("Assistant", "Identity and sales profile"),
	"widget": ("Widget", "Appearance and domains"),
	"knowledge": ("Knowledge", "Trusted sources"),
	"leads": ("Leads", "Pipeline"),
	"crm": ("Sales CRM", "Opportunities and appointments"),
	"conversations": ("Conversations", "Customer interactions"),
	"commerce": ("Commerce", "Customers, products and quotations"),
	"quotes": ("AI Quote Requests", "Approvals"),
	"usage": ("Usage", "AI credit activity"),
	"billing": ("Billing", "Plan and payments"),
	"email": ("Email", "Notifications"),
	"whatsapp": ("WhatsApp", "Channel setup"),
	"team": ("Team", "Workspace access"),
	"account": ("Account", "Business profile"),
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
