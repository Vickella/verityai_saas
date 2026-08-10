import hashlib
import ipaddress
import secrets
import socket
from urllib.parse import urlsplit

import frappe
from frappe.utils import cint, now_datetime, validate_email_address

from verityai_saas.api._response import RateLimitExceeded

from verityai_saas.services import engine
from verityai_saas.services.entitlements import require_workspace_feature, subscription_entitled, workspace_context

API_SCOPES = {"leads:read", "analytics:read"}


def _password_present(doc, fieldname):
	try:
		return bool(doc.get_password(fieldname, raise_exception=False))
	except Exception:
		return False


def _public_https_url(value, label, allow_empty=False):
	value = (value or "").strip().rstrip("/")
	if not value and allow_empty:
		return ""
	parts = urlsplit(value)
	if parts.scheme != "https" or not parts.hostname or parts.username or parts.password or parts.port not in (None, 443):
		frappe.throw(f"{label} must be a public HTTPS URL on port 443.", frappe.ValidationError)
	try:
		addresses = {item[4][0] for item in socket.getaddrinfo(parts.hostname, 443, type=socket.SOCK_STREAM)}
	except OSError:
		frappe.throw(f"{label} hostname could not be resolved.", frappe.ValidationError)
	if not addresses or any(not ipaddress.ip_address(value).is_global for value in addresses):
		frappe.throw(f"{label} must resolve only to public addresses.", frappe.ValidationError)
	return value


def integration_status(workspace):
	context = workspace_context(workspace_name=workspace)
	config = engine.get_engine_configuration(workspace)
	setting_name = frappe.db.get_value("VerityAI Notification Setting", {"workspace": workspace}, "name")
	setting = frappe.get_doc("VerityAI Notification Setting", setting_name) if setting_name else None
	plan = context.plan if context else None
	credentials = frappe.get_all(
		"VerityAI API Credential", filters={"workspace": workspace},
		fields=["name", "label", "token_prefix", "scopes", "active", "last_used_on", "creation"],
		order_by="creation desc", limit=100,
	)
	return {
		"features": {key: bool(plan and plan.get(key)) for key in (
			"can_bring_own_ai_provider_key", "can_use_erpnext_integration", "can_use_custom_smtp", "can_use_api_access", "can_remove_branding",
		)},
		"provider": {"provider": config.ai_provider or "OpenAI", "model": config.model_name, "base_url": config.provider_api_base or "", "api_key_present": _password_present(config, "provider_api_key"), "semantic_search_enabled": bool(config.enable_semantic_knowledge_search), "embedding_model": config.knowledge_embedding_model or "text-embedding-3-small"},
		"erpnext": {"enabled": bool(config.enable_erpnext_integration), "url": config.erpnext_url or "", "api_key_present": _password_present(config, "erpnext_api_key"), "api_secret_present": _password_present(config, "erpnext_api_secret")},
		"smtp": {"enabled": bool(setting and setting.custom_smtp_enabled), "host": setting.smtp_host if setting else "", "port": setting.smtp_port if setting else 587, "use_tls": bool(setting and setting.smtp_use_tls), "username": setting.smtp_username if setting else "", "sender_email": setting.smtp_sender_email if setting else "", "password_present": bool(setting and _password_present(setting, "smtp_password"))},
		"api_credentials": credentials,
	}


def configure_provider(workspace, values):
	require_workspace_feature(workspace, "can_bring_own_ai_provider_key", "a bring-your-own AI provider")
	provider = (values.get("provider") or "OpenAI").strip()
	if provider not in {"OpenAI", "OpenAI-Compatible"}:
		frappe.throw("Unsupported AI provider.", frappe.ValidationError)
	model = (values.get("model") or "").strip()
	if not model or len(model) > 140:
		frappe.throw("A valid model name is required.", frappe.ValidationError)
	base_url = _public_https_url(values.get("base_url"), "Provider API base URL", allow_empty=provider == "OpenAI")
	api_key = (values.get("api_key") or "").strip()
	config = engine.get_engine_configuration(workspace)
	if not api_key and not _password_present(config, "provider_api_key"):
		frappe.throw("An API key is required.", frappe.ValidationError)
	config.ai_provider = provider
	config.model_name = model
	config.provider_api_base = base_url or None
	if api_key:
		config.provider_api_key = api_key
	semantic_enabled = bool(cint(values.get("semantic_search_enabled")))
	embedding_model = (values.get("embedding_model") or "text-embedding-3-small").strip()
	if semantic_enabled and (not embedding_model or len(embedding_model) > 140):
		frappe.throw("A valid embedding model is required.", frappe.ValidationError)
	config.enable_semantic_knowledge_search = int(semantic_enabled)
	config.knowledge_embedding_provider = provider if semantic_enabled else None
	config.knowledge_embedding_model = embedding_model if semantic_enabled else None
	config.save(ignore_permissions=True)
	if semantic_enabled:
		frappe.enqueue(
			"verity_ai.knowledge_index.embed_knowledge_chunks", queue="long", enqueue_after_commit=True,
			tenant=engine.get_workspace_engine_tenant(workspace), job_name=f"Knowledge embeddings: {workspace}",
		)
	return integration_status(workspace)["provider"]


def configure_erpnext(workspace, values):
	require_workspace_feature(workspace, "can_use_erpnext_integration", "ERPNext integration")
	config = engine.get_engine_configuration(workspace)
	enabled = bool(cint(values.get("enabled")))
	if enabled:
		config.erpnext_url = _public_https_url(values.get("url") or config.erpnext_url, "ERPNext URL")
		api_key = (values.get("api_key") or "").strip()
		api_secret = (values.get("api_secret") or "").strip()
		if not api_key and not _password_present(config, "erpnext_api_key"):
			frappe.throw("ERPNext API key is required.", frappe.ValidationError)
		if not api_secret and not _password_present(config, "erpnext_api_secret"):
			frappe.throw("ERPNext API secret is required.", frappe.ValidationError)
		if api_key:
			config.erpnext_api_key = api_key
		if api_secret:
			config.erpnext_api_secret = api_secret
	config.enable_erpnext_integration = int(enabled)
	config.save(ignore_permissions=True)
	return integration_status(workspace)["erpnext"]


def _smtp_host(value):
	host = (value or "").strip().lower().rstrip(".")
	if not host or "/" in host or ":" in host:
		frappe.throw("A valid SMTP hostname is required.", frappe.ValidationError)
	try:
		addresses = {item[4][0] for item in socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)}
	except OSError:
		frappe.throw("SMTP hostname could not be resolved.", frappe.ValidationError)
	if not addresses or any(not ipaddress.ip_address(value).is_global for value in addresses):
		frappe.throw("SMTP hostname must resolve only to public addresses.", frappe.ValidationError)
	return host


def configure_smtp(workspace, values):
	require_workspace_feature(workspace, "can_use_custom_smtp", "custom SMTP")
	name = frappe.db.get_value("VerityAI Notification Setting", {"workspace": workspace}, "name")
	doc = frappe.get_doc("VerityAI Notification Setting", name) if name else frappe.get_doc({"doctype": "VerityAI Notification Setting", "workspace": workspace, "status": "Active"})
	enabled = bool(cint(values.get("enabled")))
	if enabled:
		doc.smtp_host = _smtp_host(values.get("host") or doc.smtp_host)
		doc.smtp_port = cint(values.get("port") or doc.smtp_port or 587)
		if doc.smtp_port not in {465, 587}:
			frappe.throw("SMTP port must be 465 or 587.", frappe.ValidationError)
		doc.smtp_use_tls = int(doc.smtp_port == 587)
		doc.smtp_username = (values.get("username") or doc.smtp_username or "").strip()
		sender = (values.get("sender_email") or doc.smtp_sender_email or "").strip()
		validate_email_address(sender, throw=True)
		doc.smtp_sender_email = sender
		password = values.get("password") or ""
		if not password and not _password_present(doc, "smtp_password"):
			frappe.throw("SMTP password is required.", frappe.ValidationError)
		if password:
			doc.smtp_password = password
	doc.custom_smtp_enabled = int(enabled)
	if doc.get("__islocal"):
		doc.insert(ignore_permissions=True)
	else:
		doc.save(ignore_permissions=True)
	return integration_status(workspace)["smtp"]


def normalize_scopes(value):
	values = value if isinstance(value, list) else (value or "").replace(",", " ").split()
	scopes = sorted({str(item).strip() for item in values if str(item).strip()})
	if not scopes or any(scope not in API_SCOPES for scope in scopes):
		frappe.throw("Choose at least one supported API scope.", frappe.ValidationError)
	return scopes


def create_api_credential(workspace, label, scopes):
	require_workspace_feature(workspace, "can_use_api_access", "API access")
	label = (label or "").strip()
	if not label or len(label) > 140:
		frappe.throw("A credential label is required.", frappe.ValidationError)
	if frappe.db.count("VerityAI API Credential", {"workspace": workspace, "active": 1}) >= 10:
		frappe.throw("A workspace can have at most 10 active API credentials.", frappe.ValidationError)
	token = f"vai_{secrets.token_urlsafe(32)}"
	doc = frappe.get_doc({
		"doctype": "VerityAI API Credential", "workspace": workspace, "label": label,
		"token_prefix": token[:12], "token_hash": hashlib.sha256(token.encode()).hexdigest(),
		"scopes": " ".join(normalize_scopes(scopes)), "active": 1,
	}).insert(ignore_permissions=True)
	return {"credential": doc.name, "token": token, "token_prefix": doc.token_prefix, "scopes": doc.scopes}


def revoke_api_credential(workspace, credential):
	require_workspace_feature(workspace, "can_use_api_access", "API access")
	if not frappe.db.exists("VerityAI API Credential", {"name": credential, "workspace": workspace}):
		frappe.throw("API credential was not found.", frappe.DoesNotExistError)
	frappe.db.set_value("VerityAI API Credential", credential, "active", 0)
	return {"credential": credential, "active": False}


def authenticate_api(scope):
	token = (frappe.get_request_header("X-VerityAI-API-Key") or "").strip()
	if not token:
		header = (frappe.get_request_header("Authorization") or "").strip()
		token = header[7:].strip() if header.startswith("Bearer ") else ""
	if not token:
		frappe.throw("An X-VerityAI-API-Key header is required.", frappe.AuthenticationError)
	if not token.startswith("vai_") or len(token) < 30:
		frappe.throw("The API token is invalid.", frappe.AuthenticationError)
	digest = hashlib.sha256(token.encode()).hexdigest()
	row = frappe.db.get_value("VerityAI API Credential", {"token_hash": digest, "active": 1}, ["name", "workspace", "scopes"], as_dict=True)
	if not row:
		frappe.throw("The API token is invalid or revoked.", frappe.AuthenticationError)
	if scope not in set((row.scopes or "").split()):
		frappe.throw("The API token does not include this scope.", frappe.PermissionError)
	context = workspace_context(workspace_name=row.workspace)
	if not context or not subscription_entitled(context) or not context.plan or not context.plan.can_use_api_access:
		frappe.throw("API access is not enabled for this workspace.", frappe.PermissionError)
	bucket = now_datetime().strftime("%Y%m%d%H%M")
	limit = max(cint(context.plan.public_rate_limit_per_minute or 20), 1)
	cache = frappe.cache()
	key = f"verityai_saas:api:{row.name}:{bucket}"
	count = cache.incr(key)
	if count == 1 and hasattr(cache, "expire"):
		cache.expire(key, 70)
	if count > limit:
		raise RateLimitExceeded("API rate limit exceeded.")
	frappe.db.set_value("VerityAI API Credential", row.name, "last_used_on", now_datetime(), update_modified=False)
	return context