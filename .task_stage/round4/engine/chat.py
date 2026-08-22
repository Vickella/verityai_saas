import uuid
import re

import frappe
from frappe import _
from frappe.utils import now_datetime

from verity_ai.engine.openai_handler import process_chat
from verity_ai.entitlements import EntitlementDenied
from verity_ai.tenant_security import origin_allowed_for_domains


FALLBACK_REPLY = (
	"Thank you for reaching out. The assistant service is temporarily being refreshed, "
	"but I can still help route your request. Please share your name, contact details, "
	"and what you need assistance with, and the VerityCore team will follow up."
)

COLOR_PRESETS = {
	"Verity Blue": {"primary": "#0b5ed7", "primary_dark": "#06428f"},
	"Navy": {"primary": "#123f78", "primary_dark": "#071526"},
	"Emerald": {"primary": "#0f766e", "primary_dark": "#115e59"},
	"Slate": {"primary": "#475569", "primary_dark": "#1e293b"},
	"Gold": {"primary": "#b7791f", "primary_dark": "#7c4a03"},
}

HEADER_PRESETS = {
	"Navy Gradient": "linear-gradient(135deg, #071526 0%, #10233d 58%, #123f78 100%)",
	"Blue Gradient": "linear-gradient(135deg, #05204a 0%, #0b5ed7 100%)",
	"Emerald Gradient": "linear-gradient(135deg, #052e2b 0%, #0f766e 100%)",
	"Slate Gradient": "linear-gradient(135deg, #111827 0%, #475569 100%)",
}

MAX_PUBLIC_MESSAGE_CHARS = 4000
HEX_COLOUR = re.compile(r"^#[0-9a-fA-F]{6}$")


def darken_hex(value, factor=0.58):
	value = value.lstrip("#")
	channels = [max(0, min(255, round(int(value[index:index + 2], 16) * factor))) for index in (0, 2, 4)]
	return "#" + "".join(f"{channel:02x}" for channel in channels)


def primary_colours(value):
	value = str(value or "").strip()
	if HEX_COLOUR.fullmatch(value):
		return {"primary": value.lower(), "primary_dark": darken_hex(value)}
	return COLOR_PRESETS.get(value or "Verity Blue", COLOR_PRESETS["Verity Blue"])


def header_background(value):
	value = str(value or "").strip()
	if HEX_COLOUR.fullmatch(value):
		return f"linear-gradient(135deg, {darken_hex(value, 0.42)} 0%, {value.lower()} 100%)"
	return HEADER_PRESETS.get(value or "Navy Gradient", HEADER_PRESETS["Navy Gradient"])


def get_request_origin():
	if not getattr(frappe, "request", None):
		return None
	return frappe.request.headers.get("Origin") or frappe.request.headers.get("Referer")



def row_value(row, key):
	if hasattr(row, "get"):
		return row.get(key)
	return getattr(row, key, None)


def is_origin_allowed(tenant, origin):
	allowed_domains = row_value(tenant, "allowed_domains") or []
	allowed = [row_value(domain, "domain") for domain in allowed_domains if row_value(domain, "domain")]
	return origin_allowed_for_domains(origin, allowed, require_configured=True)


def get_public_tenant(tenant_id):
	rows = frappe.get_all(
		"AI Tenant",
		filters={"name": tenant_id},
		fields=["name", "active", "assistant_name", "widget_title", "widget_greeting", "widget_primary_color", "widget_header_color", "show_branding"],
		limit=1,
		ignore_permissions=True,
	)
	if not rows:
		return None

	tenant = rows[0]
	tenant.allowed_domains = frappe.get_all("AI Allowed Domain", filters={"parent": tenant_id, "parenttype": "AI Tenant"}, fields=["domain"], order_by="idx asc", ignore_permissions=True)
	return tenant



def get_public_config(tenant_id):
	name = frappe.db.get_value("AI Configuration", {"tenant": tenant_id}, "name")
	return frappe.get_doc("AI Configuration", name) if name else None


def client_ip():
	request = getattr(frappe, "request", None)
	if not request:
		return "unknown"
	forwarded = request.headers.get("X-Forwarded-For")
	if forwarded:
		return forwarded.split(",", 1)[0].strip()
	return getattr(request, "remote_addr", None) or "unknown"


def record_rate_limit_abuse(tenant_id, identity, limit):
	try:
		from verity_ai.monitoring import create_or_update_alert

		create_or_update_alert(
			tenant_id,
			"System",
			f"public-rate-limit:{tenant_id}:{identity}",
			"Warning",
			"Public chat rate limit was exceeded.",
			{"identity": identity, "limit_per_minute": limit},
		)
	except Exception:
		frappe.log_error(title="Verity AI Rate Limit Alert Error", message=frappe.get_traceback())


def assert_public_rate_limit(config, tenant_id, session_id=None):
	limit = int(config.get("public_rate_limit_per_minute") or 20) if config else 20
	if limit <= 0:
		return
	identity = session_id or client_ip()
	bucket = now_datetime().strftime("%Y%m%d%H%M")
	key = f"verity_ai:public_rate:{tenant_id}:{identity}:{bucket}"
	try:
		cache = frappe.cache()
		count = cache.incr(key)
		if count == 1 and hasattr(cache, "expire"):
			cache.expire(key, 70)
		if count > limit:
			record_rate_limit_abuse(tenant_id, identity, limit)
			frappe.local.response["http_status_code"] = 429
			frappe.throw(_("Too many messages. Please wait a minute and try again."))
	except Exception:
		if frappe.local.response.get("http_status_code") == 429:
			raise
		frappe.log_error(title="Verity AI Rate Limit Error", message=frappe.get_traceback())

def public_fallback_response(session_id):
	frappe.local.message_log = []
	return {"success": True, "session_id": session_id, "reply": FALLBACK_REPLY, "fallback": True}


def public_error(message, status=400, session_id=None):
	frappe.local.response["http_status_code"] = status
	payload = {"success": False, "error": message}
	if session_id:
		payload["session_id"] = session_id
	return payload


def validate_public_message(message, max_chars=MAX_PUBLIC_MESSAGE_CHARS):
	message = (message or "").strip()
	if not message:
		return None, _("Message is required")
	if len(message) > int(max_chars or MAX_PUBLIC_MESSAGE_CHARS):
		return None, _("Message is too long. Please shorten it and try again.")
	return message, None

@frappe.whitelist(allow_guest=True)
def get_widget_settings(tenant_id=None):
	if not tenant_id:
		return public_error(_("Tenant ID is required"))
	tenant = get_public_tenant(tenant_id)
	if not tenant or not row_value(tenant, "active"):
		return public_error(_("Invalid or inactive tenant"), status=404)
	if not is_origin_allowed(tenant, get_request_origin()):
		return public_error("Domain not allowed", status=403)

	config = get_public_config(tenant_id)
	max_chars = int(config.get("max_public_message_chars") or MAX_PUBLIC_MESSAGE_CHARS) if config else MAX_PUBLIC_MESSAGE_CHARS
	primary = primary_colours(row_value(tenant, "widget_primary_color"))
	header = header_background(row_value(tenant, "widget_header_color"))
	return {
		"success": True,
		"assistant_name": row_value(tenant, "assistant_name") or "Verity AI",
		"title": row_value(tenant, "widget_title") or "Client Support Assistant",
		"greeting": row_value(tenant, "widget_greeting") or "Welcome. I am here to help with product information, service questions, or anything else you need.",
		"primary_color": primary["primary"],
		"primary_dark_color": primary["primary_dark"],
		"header_background": header,
		"max_message_chars": max_chars,
		"show_branding": bool(row_value(tenant, "show_branding")),
	}


@frappe.whitelist(allow_guest=True)
def send_message(tenant_id=None, message=None, session_id=None):
	if getattr(frappe.request, "method", "POST") == "OPTIONS":
		return {"success": True}

	if not tenant_id:
		return public_error(_("Tenant ID is required"))

	config = get_public_config(tenant_id)
	max_chars = int(config.get("max_public_message_chars") or MAX_PUBLIC_MESSAGE_CHARS) if config else MAX_PUBLIC_MESSAGE_CHARS
	message, validation_error = validate_public_message(message, max_chars=max_chars)
	if validation_error:
		return public_error(validation_error, status=400, session_id=session_id)

	tenant = get_public_tenant(tenant_id)
	if not tenant or not row_value(tenant, "active"):
		return public_error(_("Invalid or inactive tenant"), status=404, session_id=session_id)

	if not is_origin_allowed(tenant, get_request_origin()):
		return public_error("Domain not allowed", status=403, session_id=session_id)

	if not session_id:
		session_id = str(uuid.uuid4())

	previous_ignore_permissions = getattr(frappe.flags, "ignore_permissions", False)
	frappe.flags.ignore_permissions = True
	try:
		assert_public_rate_limit(config, tenant_id, session_id)
		reply = process_chat(tenant_name=tenant_id, session_id=session_id, message=message, platform="Web")
		return {"success": True, "session_id": session_id, "reply": reply}
	except EntitlementDenied as exc:
		return public_error(str(exc), status=402, session_id=session_id)
	except Exception:
		frappe.log_error(title="Verity AI Chat Error", message=frappe.get_traceback())
		return public_fallback_response(session_id)
	finally:
		frappe.flags.ignore_permissions = previous_ignore_permissions
