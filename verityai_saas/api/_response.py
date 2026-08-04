from functools import wraps

import frappe


def success(data=None):
	return {"success": True, "data": data if data is not None else {}, "error": None, "code": None}


def failure(message, code="VALIDATION_ERROR"):
	return {"success": False, "data": None, "error": str(message), "code": code}


def endpoint(function):
	@wraps(function)
	def wrapped(*args, **kwargs):
		try:
			return success(function(*args, **kwargs))
		except frappe.AuthenticationError as exc:
			frappe.local.response["http_status_code"] = 401
			return failure(exc, "AUTH_REQUIRED")
		except frappe.PermissionError as exc:
			status = frappe.local.response.get("http_status_code") or 403
			frappe.local.response["http_status_code"] = status
			return failure(exc, "RATE_LIMITED" if status == 429 else "WORKSPACE_FORBIDDEN")
		except frappe.DoesNotExistError as exc:
			frappe.local.response["http_status_code"] = 404
			return failure(exc, "NOT_FOUND")
		except Exception as exc:
			frappe.local.response["http_status_code"] = 400
			return failure(exc, "VALIDATION_ERROR")
	return wrapped


def json_value(value, default=None):
	if value in (None, ""):
		return default if default is not None else {}
	return frappe.parse_json(value) if isinstance(value, str) else value

