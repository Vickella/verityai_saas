from functools import wraps

import frappe


class RateLimitExceeded(frappe.PermissionError):
	pass


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
		except RateLimitExceeded as exc:
			frappe.local.response["http_status_code"] = 429
			return failure(exc, "RATE_LIMITED")
		except frappe.TooManyRequestsError as exc:
			frappe.local.response["http_status_code"] = 429
			return failure(exc or "Too many requests. Please try again later.", "RATE_LIMITED")
		except frappe.PermissionError as exc:
			frappe.local.response["http_status_code"] = 403
			return failure(exc, "WORKSPACE_FORBIDDEN")
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
