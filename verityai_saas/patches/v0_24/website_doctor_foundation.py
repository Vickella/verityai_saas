from verityai_saas.setup_doctypes import ensure_platform_settings, ensure_website_audit_doctypes


def execute():
	ensure_platform_settings()
	ensure_website_audit_doctypes()
