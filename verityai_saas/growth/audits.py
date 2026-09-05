import hashlib
import hmac
import json
from urllib.parse import urlsplit

import frappe
from frappe.utils import flt, now_datetime

from verityai_saas.growth.checks import deterministic_checks, score_findings
from verityai_saas.growth.pagespeed import run_pagespeed
from verityai_saas.growth.url_security import canonical_public_url, fetch_public_html
from verityai_saas.services import growth


AUDIT_STATUSES = {"Requested", "Running", "Completed", "Failed"}
AUDIT_TRANSITIONS = {"Requested": {"Running", "Failed"}, "Running": {"Completed", "Failed"}}
PUBLIC_SAFE_FIELDS = (
	"name", "target_host", "status", "observed_at", "completed_at", "overall_score", "pages_checked",
	"fetch_duration_ms", "provider_duration_ms", "error_code", "error_reference", "error_message",
)


def _token_digest(token):
	return hashlib.sha256(str(token or "").encode("utf-8")).hexdigest()


def _channel():
	return frappe.db.get_value("VerityAI Growth Channel", {"channel_code": "WEBSITE_DOCTOR"}, "name")


def _record_event(event_type, audit):
	if not growth._tracking_available():
		return
	growth.record_lifecycle_event(
		event_type, workspace=audit.workspace, channel=_channel(), source="website_doctor",
		object_type="VerityAI Website Audit", object_name=audit.name, correlation_id=audit.correlation_id,
		idempotency_key=f"{event_type}:{audit.name}",
		metadata={"status": audit.status, "target_host": audit.target_host, "overall_score": audit.overall_score},
	)


def _new_audit(url, request_kind, workspace=None, requested_by=None):
	canonical = canonical_public_url(url)
	token = frappe.generate_hash(length=40)
	doc = frappe.get_doc({
		"doctype": "VerityAI Website Audit",
		"workspace": workspace,
		"target_url": canonical,
		"target_host": urlsplit(canonical).hostname,
		"request_kind": request_kind,
		"status": "Requested",
		"requested_by_user": requested_by if requested_by and requested_by != "Guest" else None,
		"correlation_id": frappe.generate_hash(length=32),
		"public_token_hash": _token_digest(token),
	}).insert(ignore_permissions=True)
	_record_event("audit.requested", doc)
	frappe.enqueue(
		"verityai_saas.growth.audits.process_audit", queue="long", enqueue_after_commit=True,
		audit_name=doc.name, job_name=f"website-audit-{doc.name}",
	)
	return {"audit": doc.name, "token": token, "status": doc.status, "target_host": doc.target_host}


def request_public_audit(url):
	if not growth.feature_flags().get("public_audits_enabled"):
		frappe.throw("Public Website Doctor audits are not available yet.", frappe.PermissionError)
	return _new_audit(url, "Public")


def request_workspace_audit(workspace, url, user=None):
	if not growth.feature_flags().get("public_audits_enabled"):
		frappe.throw("Website Doctor audits are not available yet.", frappe.PermissionError)
	return _new_audit(url, "Workspace", workspace=workspace, requested_by=user or frappe.session.user)


def request_operator_audit(url, user=None):
	if not growth.feature_flags().get("website_doctor_internal_enabled"):
		frappe.throw("Internal Website Doctor audits are disabled.", frappe.PermissionError)
	return _new_audit(url, "Operator", requested_by=user or frappe.session.user)


def _safe_result(doc):
	data = {fieldname: doc.get(fieldname) for fieldname in PUBLIC_SAFE_FIELDS}
	if doc.status == "Completed" and doc.result_json:
		result = frappe.parse_json(doc.result_json)
		data["category_scores"] = result.get("category_scores") or {}
		data["findings"] = result.get("findings") or []
	return data


def public_status(audit_name, token):
	doc = frappe.get_doc("VerityAI Website Audit", audit_name)
	if not token or not hmac.compare_digest(_token_digest(token), str(doc.public_token_hash or "")):
		frappe.throw("Website audit link is invalid.", frappe.PermissionError)
	return _safe_result(doc)


def workspace_audits(workspace):
	rows = frappe.get_all("VerityAI Website Audit", filters={"workspace": workspace}, pluck="name", order_by="creation desc", limit_page_length=100)
	return [_safe_result(frappe.get_doc("VerityAI Website Audit", name)) for name in rows]


def workspace_audit(workspace, audit_name):
	name = frappe.db.get_value("VerityAI Website Audit", {"name": audit_name, "workspace": workspace}, "name")
	if not name:
		frappe.throw("Website audit was not found in this workspace.", frappe.DoesNotExistError)
	return _safe_result(frappe.get_doc("VerityAI Website Audit", name))


def _store_evidence(audit, findings, observed_at):
	frappe.db.delete("VerityAI Website Audit Evidence", {"audit": audit.name})
	for finding in findings:
		frappe.get_doc({
			"doctype": "VerityAI Website Audit Evidence",
			"audit": audit.name,
			"workspace": audit.workspace,
			"category": finding["category"],
			"check_code": finding["check_code"],
			"status": finding["status"],
			"source": finding["source"],
			"summary": finding["summary"],
			"evidence_json": json.dumps(finding.get("measured") or {}, separators=(",", ":"), sort_keys=True),
			"observed_at": observed_at,
		}).insert(ignore_permissions=True)


def process_audit(audit_name):
	doc = frappe.get_doc("VerityAI Website Audit", audit_name)
	if doc.status == "Completed":
		return _safe_result(doc)
	if doc.status not in {"Requested", "Running"}:
		frappe.throw("Website audit cannot be processed from its current state.", frappe.ValidationError)
	if doc.status == "Requested":
		doc.status = "Running"
		doc.save(ignore_permissions=True)
		frappe.db.commit()
	try:
		fetched = fetch_public_html(doc.target_url)
		observed_at = now_datetime()
		findings = deterministic_checks(fetched)
		provider_duration, provider_cost = 0, 0
		try:
			provider_findings, provider_duration, provider_cost = run_pagespeed(fetched.url)
			if provider_findings:
				findings.extend(provider_findings)
			else:
				findings.append({
					"category": "Performance", "check_code": "pagespeed_provider", "status": "Unavailable",
					"source": "PageSpeed", "summary": "PageSpeed measurement is not configured for this environment.",
					"measured": {"available": False}, "recommendation": "Configure the PageSpeed provider before using performance results.",
				})
		except Exception:
			findings.append({
				"category": "Performance", "check_code": "pagespeed_provider", "status": "Unavailable",
				"source": "PageSpeed", "summary": "PageSpeed measurements were unavailable for this audit.",
				"measured": {"available": False}, "recommendation": "Retry the external performance measurement later.",
			})
		overall_score, category_scores = score_findings(findings)
		_store_evidence(doc, findings, observed_at)
		doc.observed_at = observed_at
		doc.completed_at = now_datetime()
		doc.overall_score = overall_score
		doc.pages_checked = 1
		doc.response_bytes = len(fetched.body)
		doc.fetch_duration_ms = fetched.duration_ms
		doc.provider_duration_ms = provider_duration
		doc.provider_cost_usd = flt(provider_cost, 6)
		doc.result_json = json.dumps({
			"schema_version": 1,
			"category_scores": category_scores,
			"findings": [{key: value for key, value in finding.items() if key != "measured"} for finding in findings],
		}, separators=(",", ":"), sort_keys=True)
		doc.status = "Completed"
		doc.save(ignore_permissions=True)
		_record_event("audit.completed", doc)
		frappe.db.commit()
		return _safe_result(doc)
	except Exception as exc:
		frappe.db.rollback()
		doc = frappe.get_doc("VerityAI Website Audit", audit_name)
		doc.status = "Failed"
		doc.completed_at = now_datetime()
		doc.error_code = "TARGET_REJECTED" if isinstance(exc, (frappe.PermissionError, frappe.ValidationError)) else "AUDIT_FAILED"
		doc.error_reference = frappe.generate_hash(length=12).upper()
		doc.error_message = "The website could not be audited safely." if doc.error_code == "TARGET_REJECTED" else "The audit could not be completed."
		doc.save(ignore_permissions=True)
		_record_event("audit.failed", doc)
		frappe.log_error(title=f"Website audit failed [{doc.error_reference}]", message=frappe.get_traceback())
		frappe.db.commit()
		return _safe_result(doc)


def validate_audit_document(doc, method=None):
	doc.target_url = canonical_public_url(doc.target_url)
	doc.target_host = urlsplit(doc.target_url).hostname
	if doc.status not in AUDIT_STATUSES:
		frappe.throw("Website audit status is invalid.", frappe.ValidationError)
	if doc.request_kind == "Public" and (doc.workspace or doc.requested_by_user):
		frappe.throw("Public audits cannot be bound to a private workspace or user.", frappe.ValidationError)
	if doc.request_kind == "Workspace" and not doc.workspace:
		frappe.throw("Workspace audits require a workspace boundary.", frappe.ValidationError)
	if len(str(doc.public_token_hash or "")) != 64:
		frappe.throw("Website audit access token is invalid.", frappe.ValidationError)
	if doc.status == "Completed":
		if not doc.observed_at or not doc.completed_at or not doc.result_json:
			frappe.throw("Completed audits require measured results and timestamps.", frappe.ValidationError)
		try:
			result = json.loads(doc.result_json)
		except (TypeError, ValueError):
			frappe.throw("Completed audit result must be valid JSON.", frappe.ValidationError)
		if not isinstance(result, dict) or not 0 <= flt(doc.overall_score) <= 100:
			frappe.throw("Completed audit result is invalid.", frappe.ValidationError)
		doc.result_json = json.dumps(result, separators=(",", ":"), sort_keys=True)
	if doc.status == "Failed" and (not doc.completed_at or not doc.error_code or not doc.error_reference):
		frappe.throw("Failed audits require a safe error code, reference and timestamp.", frappe.ValidationError)
	previous = doc.get_doc_before_save()
	if previous and previous.status in {"Completed", "Failed"}:
		frappe.throw("Completed and failed website audits are immutable.", frappe.PermissionError)
	if previous and previous.status != doc.status and doc.status not in AUDIT_TRANSITIONS.get(previous.status, set()):
		frappe.throw(f"Website audit cannot move from {previous.status} to {doc.status}.", frappe.ValidationError)
	if previous:
		for fieldname in ("workspace", "target_url", "request_kind", "requested_by_user", "correlation_id", "public_token_hash"):
			if previous.get(fieldname) != doc.get(fieldname):
				frappe.throw("Website audit request identity is immutable.", frappe.PermissionError)


def validate_evidence_document(doc, method=None):
	if not doc.is_new():
		frappe.throw("Website audit evidence is immutable.", frappe.PermissionError)
	audit_workspace = frappe.db.get_value("VerityAI Website Audit", doc.audit, "workspace")
	if audit_workspace != doc.workspace:
		frappe.throw("Audit evidence must use the audit workspace boundary.", frappe.ValidationError)
	try:
		measured = json.loads(doc.evidence_json)
	except (TypeError, ValueError):
		frappe.throw("Audit evidence must contain valid JSON.", frappe.ValidationError)
	if not isinstance(measured, dict):
		frappe.throw("Audit evidence must be a JSON object.", frappe.ValidationError)
	doc.evidence_json = json.dumps(measured, separators=(",", ":"), sort_keys=True)


def protect_audit_delete(doc, method=None):
	frappe.throw("Website audits are retained under the controlled evidence policy.", frappe.PermissionError)


def protect_evidence_delete(doc, method=None):
	frappe.throw("Website audit evidence is immutable.", frappe.PermissionError)
