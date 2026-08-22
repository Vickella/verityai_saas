import frappe

from verityai_saas.setup_doctypes import ensure_platform_settings


def execute():
	ensure_platform_settings()
	frappe.clear_cache(doctype="VerityAI Platform Settings")
