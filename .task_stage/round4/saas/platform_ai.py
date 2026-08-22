import frappe
from frappe import _


SETTINGS_DOCTYPE = "VerityAI Platform Settings"
DEFAULT_MODEL = "gpt-4.1-mini"
DEFAULT_EMBEDDING_MODEL = "text-embedding-3-small"


def _password(doc, fieldname):
	try:
		return doc.get_password(fieldname, raise_exception=False) or ""
	except Exception:
		return ""


def configuration_status():
	settings = frappe.get_single(SETTINGS_DOCTYPE)
	return {
		"provider": settings.get("ai_provider") or "OpenAI",
		"model": settings.get("ai_model") or DEFAULT_MODEL,
		"api_base": settings.get("ai_api_base") or "",
		"embedding_model": settings.get("ai_embedding_model") or DEFAULT_EMBEDDING_MODEL,
		"api_key_present": bool(_password(settings, "ai_api_key")),
	}


def apply_to_configuration(config, settings=None, api_key=None):
	settings = settings or frappe.get_single(SETTINGS_DOCTYPE)
	api_key = api_key if api_key is not None else _password(settings, "ai_api_key")
	if not api_key:
		return False
	config.ai_provider = settings.get("ai_provider") or "OpenAI"
	config.model_name = settings.get("ai_model") or DEFAULT_MODEL
	config.provider_api_base = settings.get("ai_api_base") or ""
	config.knowledge_embedding_model = settings.get("ai_embedding_model") or DEFAULT_EMBEDDING_MODEL
	config.provider_api_key = api_key
	config.save(ignore_permissions=True)
	return True


def configure(values):
	values = frappe._dict(values or {})
	provider = (values.provider or "OpenAI").strip()
	if provider not in {"OpenAI", "OpenAI-Compatible"}:
		frappe.throw(_("Unsupported AI provider."), frappe.ValidationError)
	model = (values.model or "").strip()
	if not model:
		frappe.throw(_("Model is required."), frappe.ValidationError)
	api_base = (values.api_base or "").strip()
	if provider == "OpenAI-Compatible" and not api_base.startswith("https://"):
		frappe.throw(_("An HTTPS API base URL is required."), frappe.ValidationError)
	if provider == "OpenAI":
		api_base = ""

	settings = frappe.get_single(SETTINGS_DOCTYPE)
	api_key = (values.api_key or "").strip()
	current_key = _password(settings, "ai_api_key")
	if not api_key and not current_key:
		frappe.throw(_("API key is required."), frappe.ValidationError)

	settings.ai_provider = provider
	settings.ai_model = model
	settings.ai_api_base = api_base
	settings.ai_embedding_model = (values.embedding_model or DEFAULT_EMBEDDING_MODEL).strip()
	if api_key:
		settings.ai_api_key = api_key
	settings.save(ignore_permissions=True)

	active_key = api_key or current_key
	updated = 0
	for name in frappe.get_all("AI Configuration", pluck="name"):
		if apply_to_configuration(frappe.get_doc("AI Configuration", name), settings=settings, api_key=active_key):
			updated += 1
	frappe.clear_cache(doctype=SETTINGS_DOCTYPE)
	return {**configuration_status(), "configurations_updated": updated}
