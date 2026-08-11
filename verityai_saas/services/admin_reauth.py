import hashlib

import frappe
from frappe import _
from frappe.auth import LoginAttemptTracker
from frappe.utils.password import check_password

from verityai_saas.services.permissions import require_operator


UNLOCK_SECONDS = 15 * 60
MAX_FAILURES = 5


def _session_fingerprint():
	user = require_operator()
	sid = getattr(frappe.session, "sid", None)
	if not sid or sid == "Guest":
		frappe.throw(_("A valid authenticated session is required."), frappe.AuthenticationError)
	payload = f"{frappe.local.site}|{sid}|{user}".encode()
	return hashlib.sha256(payload).hexdigest()


def _unlock_key():
	return f"verityai_saas:admin_reauth:{_session_fingerprint()}"


def _attempt_key():
	request_ip = getattr(frappe.local, "request_ip", None) or "unknown"
	payload = f"{_session_fingerprint()}|{request_ip}".encode()
	return f"verityai_saas:admin_reauth_attempt:{hashlib.sha256(payload).hexdigest()}"


def is_admin_reauthenticated():
	try:
		return bool(frappe.cache.get_value(_unlock_key()))
	except frappe.AuthenticationError:
		return False


def mark_admin_reauthenticated():
	"""Mark only the current authenticated session as recently re-verified."""
	frappe.cache.set_value(_unlock_key(), 1, expires_in_sec=UNLOCK_SECONDS)
	return True


def clear_admin_reauthentication():
	frappe.cache.delete_value(_unlock_key())
	return True


def require_admin_reauthentication():
	require_operator()
	if not is_admin_reauthenticated():
		frappe.throw(_("Administrator password confirmation is required."), frappe.AuthenticationError)
	return frappe.session.user


def verify_administrator_password(password):
	require_operator()
	password = str(password or "")
	if not password:
		frappe.throw(_("Administrator password is required."), frappe.ValidationError)
	tracker = LoginAttemptTracker(_attempt_key(), max_consecutive_login_attempts=MAX_FAILURES - 1, lock_interval=UNLOCK_SECONDS)
	if not tracker.is_user_allowed():
		frappe.throw(_("Too many failed attempts. Try again in 15 minutes."), frappe.AuthenticationError)
	try:
		check_password("Administrator", password, delete_tracker_cache=False)
	except frappe.AuthenticationError:
		tracker.add_failure_attempt()
		frappe.logger("verityai_saas.security").warning(
			"Failed operator-console re-authentication user=%s ip=%s",
			frappe.session.user,
			getattr(frappe.local, "request_ip", None) or "unknown",
		)
		frappe.throw(_("Administrator password is incorrect."), frappe.AuthenticationError)
	tracker.add_success_attempt()
	mark_admin_reauthenticated()
	return {"unlocked": True, "expires_in_seconds": UNLOCK_SECONDS}
