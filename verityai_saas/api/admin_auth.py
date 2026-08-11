import frappe

from verityai_saas.api._response import endpoint
from verityai_saas.services.admin_reauth import (
	clear_admin_reauthentication,
	is_admin_reauthenticated,
	verify_administrator_password,
)
from verityai_saas.services.permissions import require_operator


@frappe.whitelist()
@endpoint
def status():
	require_operator()
	return {"unlocked": is_admin_reauthenticated()}


@frappe.whitelist(methods=["POST"])
@endpoint
def unlock(password):
	return verify_administrator_password(password)


@frappe.whitelist(methods=["POST"])
@endpoint
def lock():
	require_operator()
	clear_admin_reauthentication()
	return {"unlocked": False}
