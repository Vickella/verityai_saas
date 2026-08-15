import json

import frappe
from frappe.utils import now_datetime

from verityai_saas.services import engine
from verityai_saas.services.permissions import check_workspace_access


OPEN_ALERT_STATUSES = ("Open", "Acknowledged")


def workspace_health(workspace_name, status=None, severity=None, limit=100, user=None):
	workspace = check_workspace_access(workspace_name, user)
	tenant = engine.get_workspace_engine_tenant(workspace.name)
	settings = engine.safe_settings(workspace.name, include_configuration=True)
	configuration = settings.get("configuration") or {}
	alert_filters = {"status": status, "severity": severity, "limit": limit}
	alerts = engine.get_workspace_alerts(workspace.name, alert_filters)
	open_alerts = frappe.db.count(
		"AI Monitoring Alert",
		{"tenant": tenant, "status": ["in", list(OPEN_ALERT_STATUSES)]},
	)
	critical_alerts = frappe.db.count(
		"AI Monitoring Alert",
		{
			"tenant": tenant,
			"status": ["in", list(OPEN_ALERT_STATUSES)],
			"severity": "Critical",
		},
	)
	subscription = frappe.db.get_value(
		"VerityAI Subscription",
		{"workspace": workspace.name},
		["plan", "status", "trial_end", "current_period_end"],
		as_dict=True,
		order_by="creation desc",
	)
	wallet = frappe.db.get_value(
		"VerityAI Usage Wallet",
		{"workspace": workspace.name},
		["status", "tokens_used", "tokens_remaining", "last_synced_from_usage_logs"],
		as_dict=True,
	)
	whatsapp = frappe.db.get_value(
		"VerityAI WhatsApp Setup",
		{"workspace": workspace.name},
		["mode", "setup_status", "last_tested_on"],
		as_dict=True,
	)
	engine_active = bool(settings.get("active"))
	monitoring_enabled = bool(configuration.get("enable_monitoring_alerts"))
	overall_status = _overall_status(
		workspace.status,
		engine_active,
		critical_alerts,
		open_alerts,
		monitoring_enabled,
		wallet.status if wallet else None,
		subscription.status if subscription else None,
	)
	return {
		"overall_status": overall_status,
		"workspace_status": workspace.status,
		"engine_active": engine_active,
		"monitoring_enabled": monitoring_enabled,
		"open_alerts": open_alerts,
		"critical_alerts": critical_alerts,
		"total_alerts": frappe.db.count("AI Monitoring Alert", {"tenant": tenant}),
		"subscription": subscription,
		"wallet": wallet,
		"whatsapp": whatsapp,
		"alerts": alerts,
		"generated_at": now_datetime(),
	}


def _overall_status(workspace_status, engine_active, critical_alerts, open_alerts, monitoring_enabled, wallet_status, subscription_status):
	if not engine_active or workspace_status == "Suspended" or critical_alerts:
		return "Critical"
	if not monitoring_enabled or open_alerts or wallet_status in {"Warning", "Exhausted", "Suspended"} or subscription_status in {
		"Past Due", "Suspended", "Expired",
	}:
		return "Attention"
	return "Healthy"


def update_workspace_alert(workspace_name, alert_name, status, note=None, allow_operator=False):
	workspace = check_workspace_access(workspace_name, allow_operator=allow_operator)
	status = (status or "").strip()
	if status not in {"Acknowledged", "Resolved"}:
		frappe.throw("Alert status must be Acknowledged or Resolved.", frappe.ValidationError)
	tenant = engine.get_workspace_engine_tenant(workspace.name)
	if not frappe.db.exists("AI Monitoring Alert", {"name": alert_name, "tenant": tenant}):
		frappe.throw("Monitoring alert was not found.", frappe.DoesNotExistError)
	alert = frappe.get_doc("AI Monitoring Alert", alert_name)
	if alert.status == "Resolved" and status == "Acknowledged":
		frappe.throw("A resolved alert cannot be moved back to Acknowledged.", frappe.ValidationError)
	if note:
		try:
			details = json.loads(alert.details_json or "{}")
		except Exception:
			details = {"previous_details": str(alert.details_json or "")[:1000]}
		notes = details.get("operator_notes") or []
		notes.append({"user": frappe.session.user, "note": str(note).strip()[:1000], "timestamp": str(now_datetime())})
		details["operator_notes"] = notes[-50:]
		alert.details_json = frappe.as_json(details)
	alert.status = status
	alert.save(ignore_permissions=True)
	return {"alert": alert.name, "status": alert.status}
