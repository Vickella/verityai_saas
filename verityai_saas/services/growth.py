import hashlib
import hmac
import json
import re

import frappe
from frappe.utils import cint, flt, get_datetime, now_datetime


FEATURE_FLAGS = (
	"growth_foundation_enabled",
	"public_audits_enabled",
	"website_builder_enabled",
	"partner_portal_enabled",
	"white_label_enabled",
	"outbound_enabled",
)
CHANNEL_TYPES = {"Owned", "Product", "Messaging", "Partner", "Community", "Marketplace", "Integration"}
DELIVERY_MODES = {"Public", "Automated", "Human Operated", "Human Approved", "Embedded", "Partner Managed"}
RISK_CLASSES = {"Low", "Moderate", "High"}
CHANNEL_STATUSES = {"Active", "Paused", "Archived"}
CAMPAIGN_OBJECTIVES = {"Awareness", "Acquisition", "Activation", "Referral", "Revenue", "Retention"}
CAMPAIGN_STATUSES = {"Draft", "Active", "Paused", "Completed", "Archived"}
SUBJECT_TYPES = {"Visitor", "User", "Lead", "Customer", "Partner"}
CONSENT_STATUSES = {"Granted", "Withdrawn", "Expired"}
CODE_PATTERN = re.compile(r"^[A-Z0-9][A-Z0-9_-]{1,39}$")
EVENT_PATTERN = re.compile(r"^[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*){1,4}$")
PLATFORM_CHANNELS = {"web": "WIDGET", "whatsapp": "WHATSAPP", "desk": "CRM"}
LEAD_STATUS_EVENTS = {
	"Contacted": "lead.contacted",
	"Qualified": "lead.qualified",
	"Won": "lead.won",
	"Lost": "lead.lost",
}
OPPORTUNITY_STAGE_EVENTS = {
	"Qualified": "opportunity.qualified",
	"Proposal": "opportunity.proposal",
	"Negotiation": "opportunity.negotiation",
	"Won": "opportunity.won",
	"Lost": "opportunity.lost",
}
ATTRIBUTION_FIELDS = ("source", "medium", "content", "term", "referral_code")

DEFAULT_CHANNELS = (
	("WEBSITE", "Verity website", "Owned", "Public", "Low", "landing pages, forms, campaign attribution"),
	("WEBSITE_DOCTOR", "Website Doctor", "Product", "Public", "High", "bounded audits, reports, redesign conversion"),
	("WIDGET", "Website widget", "Product", "Embedded", "Moderate", "assistant conversations and lead capture"),
	("WHATSAPP", "WhatsApp AI", "Messaging", "Automated", "High", "consented inbound replies and approved templates"),
	("CRM", "Verity CRM", "Owned", "Human Operated", "Moderate", "lead assignment, follow-up, opportunity management"),
	("EMAIL", "Email", "Messaging", "Human Approved", "High", "transactional and consented marketing delivery"),
	("VERITY_BADGE", "Powered by Verity badge", "Product", "Embedded", "Low", "signed attribution links and badge events"),
	("REFERRAL", "Customer referrals", "Partner", "Partner Managed", "Moderate", "referral links and settled rewards"),
	("AFFILIATE", "Affiliate programme", "Partner", "Partner Managed", "High", "approved promotion and commission attribution"),
	("SOCIAL_COMMUNITY", "Social and community", "Community", "Human Operated", "Moderate", "useful human participation only"),
	("DIRECT_OUTBOUND", "Direct outbound", "Messaging", "Human Approved", "High", "reviewed outreach with suppression enforcement"),
	("WORKSHOPS", "Workshops and resources", "Owned", "Human Operated", "Moderate", "registrations, resources, consented follow-up"),
	("SHOWCASE", "Customer showcase", "Product", "Public", "Moderate", "customer-approved examples and case studies"),
	("TEMPLATE_MARKETPLACE", "Template marketplace", "Marketplace", "Partner Managed", "High", "reviewed creator submissions"),
	("INTEGRATIONS", "Integration ecosystem", "Integration", "Partner Managed", "High", "reviewed provider and developer integrations"),
	("OPEN_SOURCE", "Open-source ecosystem", "Community", "Public", "Moderate", "approved edge components and releases"),
	("HOSTING_PARTNERS", "Hosting and domain partners", "Partner", "Partner Managed", "High", "scoped provisioning and reconciliation"),
)


def _clean(value, max_length=140):
	return str(value or "").strip()[:max_length]


def _required(value, label, max_length=140):
	value = _clean(value, max_length)
	if not value:
		frappe.throw(f"{label} is required.", frappe.ValidationError)
	return value


def _choice(value, allowed, label):
	value = _required(value, label)
	if value not in allowed:
		frappe.throw(f"Unsupported {label.lower()}.", frappe.ValidationError)
	return value


def _code(value, label):
	value = _required(value, label).upper().replace(" ", "_")
	if not CODE_PATTERN.fullmatch(value):
		frappe.throw(f"{label} must be 2-40 uppercase letters, numbers, underscores, or hyphens.", frappe.ValidationError)
	return value


def _non_negative(value, label, integer=False):
	number = cint(value) if integer else flt(value)
	if number < 0:
		frappe.throw(f"{label} cannot be negative.", frappe.ValidationError)
	return number


def _identity_hash(identifier):
	identifier = _required(identifier, "Subject identifier", 500).casefold()
	pepper = (getattr(frappe.local, "conf", {}) or {}).get("encryption_key")
	if not pepper:
		frappe.throw("Growth privacy records require the site encryption key.", frappe.ValidationError)
	pepper = str(pepper)
	return hmac.new(pepper.encode(), identifier.encode(), hashlib.sha256).hexdigest()


def feature_flags():
	settings = frappe.get_single("VerityAI Platform Settings")
	return {name: bool(cint(settings.get(name))) for name in FEATURE_FLAGS}


def configure_feature_flags(values):
	values = values or {}
	settings = frappe.get_single("VerityAI Platform Settings")
	for name in FEATURE_FLAGS:
		if name in values:
			settings.set(name, 1 if cint(values.get(name)) else 0)
	settings.save(ignore_permissions=True)
	return feature_flags()


def seed_default_channels():
	for code, name, channel_type, delivery_mode, risk_class, actions in DEFAULT_CHANNELS:
		if frappe.db.exists("VerityAI Growth Channel", {"channel_code": code}):
			continue
		frappe.get_doc({
			"doctype": "VerityAI Growth Channel",
			"channel_code": code,
			"channel_name": name,
			"channel_type": channel_type,
			"delivery_mode": delivery_mode,
			"risk_class": risk_class,
			"status": "Active",
			"allowed_actions": actions,
		}).insert(ignore_permissions=True)


def save_channel(values, channel=None):
	values = values or {}
	if channel:
		if not frappe.db.exists("VerityAI Growth Channel", channel):
			frappe.throw("Growth channel was not found.", frappe.DoesNotExistError)
		doc = frappe.get_doc("VerityAI Growth Channel", channel)
	else:
		doc = frappe.new_doc("VerityAI Growth Channel")
		doc.channel_code = _code(values.get("channel_code"), "Channel code")

	doc.channel_name = _required(values.get("channel_name") or doc.channel_name, "Channel name")
	doc.channel_type = _choice(values.get("channel_type") or doc.channel_type, CHANNEL_TYPES, "Channel type")
	doc.delivery_mode = _choice(values.get("delivery_mode") or doc.delivery_mode, DELIVERY_MODES, "Delivery mode")
	doc.risk_class = _choice(values.get("risk_class") or doc.risk_class or "Low", RISK_CLASSES, "Risk class")
	doc.status = _choice(values.get("status") or doc.status or "Active", CHANNEL_STATUSES, "Channel status")
	doc.owner_user = _clean(values.get("owner_user") if "owner_user" in values else doc.owner_user)
	doc.adapter = _clean(values.get("adapter") if "adapter" in values else doc.adapter)
	doc.allowed_actions = _clean(values.get("allowed_actions") if "allowed_actions" in values else doc.allowed_actions, 1000)
	doc.monthly_limit = _non_negative(values.get("monthly_limit", doc.monthly_limit), "Monthly delivery limit", integer=True)
	doc.notes = _clean(values.get("notes") if "notes" in values else doc.notes, 2000)
	doc.save(ignore_permissions=True) if channel else doc.insert(ignore_permissions=True)
	return channel_data(doc)


def save_campaign(values, campaign=None):
	values = values or {}
	if campaign:
		if not frappe.db.exists("VerityAI Growth Campaign", campaign):
			frappe.throw("Growth campaign was not found.", frappe.DoesNotExistError)
		doc = frappe.get_doc("VerityAI Growth Campaign", campaign)
	else:
		doc = frappe.new_doc("VerityAI Growth Campaign")
		doc.campaign_code = _code(values.get("campaign_code"), "Campaign code")

	doc.campaign_name = _required(values.get("campaign_name") or doc.campaign_name, "Campaign name")
	doc.channel = _required(values.get("channel") or doc.channel, "Channel")
	if not frappe.db.exists("VerityAI Growth Channel", doc.channel):
		frappe.throw("Growth channel was not found.", frappe.DoesNotExistError)
	doc.objective = _choice(values.get("objective") or doc.objective, CAMPAIGN_OBJECTIVES, "Campaign objective")
	doc.status = _choice(values.get("status") or doc.status or "Draft", CAMPAIGN_STATUSES, "Campaign status")
	doc.audience = _clean(values.get("audience") if "audience" in values else doc.audience, 1000)
	for fieldname in ("source", "medium", "content", "term", "owner_user"):
		setattr(doc, fieldname, _clean(values.get(fieldname) if fieldname in values else doc.get(fieldname)))
	for fieldname in ("starts_on", "ends_on"):
		if fieldname in values:
			setattr(doc, fieldname, values.get(fieldname) or None)
	if doc.starts_on and doc.ends_on and get_datetime(doc.ends_on) < get_datetime(doc.starts_on):
		frappe.throw("Campaign end date cannot be before its start date.", frappe.ValidationError)
	doc.budget = _non_negative(values.get("budget", doc.budget), "Budget")
	doc.currency = _clean(values.get("currency") or doc.currency or "USD", 3).upper()
	doc.delivery_limit = _non_negative(values.get("delivery_limit", doc.delivery_limit), "Delivery limit", integer=True)
	doc.notes = _clean(values.get("notes") if "notes" in values else doc.notes, 2000)
	doc.save(ignore_permissions=True) if campaign else doc.insert(ignore_permissions=True)
	return campaign_data(doc)


def channel_data(doc):
	return {fieldname: doc.get(fieldname) for fieldname in (
		"name", "channel_name", "channel_code", "channel_type", "delivery_mode", "risk_class", "status",
		"owner_user", "adapter", "allowed_actions", "monthly_limit", "notes", "modified",
	)}


def campaign_data(doc):
	return {fieldname: doc.get(fieldname) for fieldname in (
		"name", "campaign_name", "campaign_code", "channel", "objective", "audience", "source", "medium",
		"content", "term", "starts_on", "ends_on", "budget", "currency", "delivery_limit", "owner_user",
		"status", "notes", "modified",
	)}


def record_event(event_type, **values):
	if not EVENT_PATTERN.fullmatch(_required(event_type, "Event type")):
		frappe.throw("Event type must use a dotted lowercase namespace, for example audit.completed.", frappe.ValidationError)
	idempotency_key = _clean(values.get("idempotency_key") or frappe.generate_hash(length=40))
	existing = frappe.db.get_value("VerityAI Growth Event", {"idempotency_key": idempotency_key}, "name")
	if existing:
		return frappe.get_doc("VerityAI Growth Event", existing)
	metadata = values.get("metadata") or {}
	if not isinstance(metadata, (dict, list)):
		frappe.throw("Event metadata must be a JSON object or array.", frappe.ValidationError)
	metadata_json = json.dumps(metadata, separators=(",", ":"), sort_keys=True)
	if len(metadata_json.encode()) > 8192:
		frappe.throw("Event metadata cannot exceed 8 KB.", frappe.ValidationError)
	for fieldname, doctype in (("channel", "VerityAI Growth Channel"), ("campaign", "VerityAI Growth Campaign"), ("workspace", "VerityAI Workspace"), ("account", "VerityAI Account")):
		value = values.get(fieldname)
		if value and not frappe.db.exists(doctype, value):
			frappe.throw(f"{fieldname.replace('_', ' ').title()} was not found.", frappe.DoesNotExistError)
	return frappe.get_doc({
		"doctype": "VerityAI Growth Event",
		"event_type": event_type,
		"occurred_at": values.get("occurred_at") or now_datetime(),
		"visitor_id": _clean(values.get("visitor_id")),
		"account": values.get("account"), "workspace": values.get("workspace"),
		"channel": values.get("channel"), "campaign": values.get("campaign"),
		"referral_code": _clean(values.get("referral_code")),
		"source": _clean(values.get("source")), "medium": _clean(values.get("medium")),
		"content": _clean(values.get("content")), "term": _clean(values.get("term")),
		"object_type": _clean(values.get("object_type")), "object_name": _clean(values.get("object_name")),
		"correlation_id": _clean(values.get("correlation_id")),
		"idempotency_key": idempotency_key,
		"metadata": metadata_json,
	}).insert(ignore_permissions=True)


def record_lifecycle_event(event_type, **values):
	"""Growth evidence must never interrupt a customer conversation or CRM action."""
	try:
		return record_event(event_type, **values)
	except Exception:
		frappe.log_error(frappe.get_traceback(), f"Growth lifecycle event failed: {event_type}")
		return None


def _tracking_available():
	"""Keep engine hooks harmless during install, migrations, and disabled releases."""
	try:
		return (
			frappe.db.exists("DocType", "VerityAI Growth Event")
			and frappe.db.exists("DocType", "VerityAI Growth Channel")
			and feature_flags().get("growth_foundation_enabled")
		)
	except Exception:
		return False


def _workspace_context(tenant=None, workspace=None):
	if workspace:
		return frappe.db.get_value("VerityAI Workspace", workspace, ["name", "account"], as_dict=True)
	if not tenant:
		return None
	return frappe.db.get_value(
		"VerityAI Workspace", {"engine_tenant": tenant}, ["name", "account"], as_dict=True
	)


def _channel(platform):
	code = PLATFORM_CHANNELS.get(_clean(platform).casefold())
	if not code:
		return None
	return frappe.db.get_value("VerityAI Growth Channel", {"channel_code": code}, "name")


def _safe_attribution(raw):
	if not raw:
		return {}
	if isinstance(raw, str):
		try:
			raw = json.loads(raw)
		except (TypeError, ValueError):
			return {}
	if not isinstance(raw, dict):
		return {}
	container = raw.get("attribution") if isinstance(raw.get("attribution"), dict) else raw
	return {key: _clean(container.get(key)) for key in ATTRIBUTION_FIELDS if container.get(key)}


def _lead_context(lead_name):
	if not lead_name or not frappe.db.exists("AI Lead", lead_name):
		return None, None
	lead = frappe.db.get_value(
		"AI Lead", lead_name, ["tenant", "chat_session", "source_channel"], as_dict=True
	)
	return lead, _workspace_context(tenant=lead.tenant)


def record_conversation_started(doc, method=None):
	if not _tracking_available():
		return
	context = _workspace_context(tenant=doc.get("tenant"))
	channel = _channel(doc.get("platform"))
	if not context or not channel:
		return
	record_lifecycle_event(
		"conversation.started",
		workspace=context.name,
		account=context.account,
		channel=channel,
		source=_clean(doc.get("platform")).casefold(),
		object_type="AI Chat Session",
		object_name=doc.name,
		correlation_id=doc.name,
		idempotency_key=f"conversation.started:{doc.name}",
		metadata={"platform": _clean(doc.get("platform")), "status": _clean(doc.get("status"))},
	)


def record_lead_created(doc, method=None):
	if not _tracking_available():
		return
	context = _workspace_context(tenant=doc.get("tenant"))
	channel = _channel(doc.get("source_channel"))
	if not context or not channel:
		return
	attribution = _safe_attribution(doc.get("dynamic_details"))
	record_lifecycle_event(
		"lead.captured",
		workspace=context.name,
		account=context.account,
		channel=channel,
		source=attribution.get("source") or _clean(doc.get("source_channel")).casefold(),
		medium=attribution.get("medium"),
		content=attribution.get("content"),
		term=attribution.get("term"),
		referral_code=attribution.get("referral_code"),
		object_type="AI Lead",
		object_name=doc.name,
		correlation_id=doc.get("chat_session") or doc.name,
		idempotency_key=f"lead.captured:{doc.name}",
		metadata={
			"status": _clean(doc.get("status")),
			"has_email": bool(doc.get("email")),
			"has_phone": bool(doc.get("phone")),
		},
	)


def record_lead_status(doc, method=None):
	if not _tracking_available() or not doc.has_value_changed("status"):
		return
	event_type = LEAD_STATUS_EVENTS.get(doc.get("status"))
	if not event_type:
		return
	context = _workspace_context(tenant=doc.get("tenant"))
	channel = _channel(doc.get("source_channel"))
	if not context or not channel:
		return
	record_lifecycle_event(
		event_type,
		workspace=context.name,
		account=context.account,
		channel=channel,
		source=_clean(doc.get("source_channel")).casefold(),
		object_type="AI Lead",
		object_name=doc.name,
		correlation_id=doc.get("chat_session") or doc.name,
		idempotency_key=f"{event_type}:{doc.name}",
		metadata={"status": doc.get("status")},
	)


def record_opportunity_created(doc, method=None):
	if not _tracking_available():
		return
	lead, context = _lead_context(doc.get("lead"))
	context = context or _workspace_context(workspace=doc.get("workspace"))
	if not context:
		return
	channel = _channel(lead.source_channel if lead else "CRM")
	record_lifecycle_event(
		"opportunity.created",
		workspace=context.name,
		account=context.account,
		channel=channel,
		source=_clean(doc.get("source") or (lead.source_channel if lead else "crm")).casefold(),
		object_type="VerityAI Sales Opportunity",
		object_name=doc.name,
		correlation_id=(lead.chat_session if lead else None) or doc.name,
		idempotency_key=f"opportunity.created:{doc.name}",
		metadata={"stage": doc.get("stage"), "amount": flt(doc.get("amount")), "currency": _clean(doc.get("currency"), 3)},
	)


def record_opportunity_stage(doc, method=None):
	if not _tracking_available() or not doc.has_value_changed("stage"):
		return
	event_type = OPPORTUNITY_STAGE_EVENTS.get(doc.get("stage"))
	if not event_type:
		return
	lead, context = _lead_context(doc.get("lead"))
	context = context or _workspace_context(workspace=doc.get("workspace"))
	if not context:
		return
	channel = _channel(lead.source_channel if lead else "CRM")
	record_lifecycle_event(
		event_type,
		workspace=context.name,
		account=context.account,
		channel=channel,
		source=_clean(doc.get("source") or (lead.source_channel if lead else "crm")).casefold(),
		object_type="VerityAI Sales Opportunity",
		object_name=doc.name,
		correlation_id=(lead.chat_session if lead else None) or doc.name,
		idempotency_key=f"{event_type}:{doc.name}",
		metadata={"stage": doc.get("stage"), "amount": flt(doc.get("amount")), "currency": _clean(doc.get("currency"), 3)},
	)


def record_consent(identifier, subject_type, purpose, status="Granted", **values):
	status = _choice(status, CONSENT_STATUSES, "Consent status")
	doc = frappe.get_doc({
		"doctype": "VerityAI Consent Record",
		"subject_type": _choice(subject_type, SUBJECT_TYPES, "Subject type"),
		"subject_hash": _identity_hash(identifier),
		"purpose": _required(purpose, "Purpose"),
		"channel": values.get("channel"),
		"status": status,
		"source": _clean(values.get("source")),
		"captured_on": values.get("captured_on") or now_datetime(),
		"withdrawn_on": values.get("withdrawn_on") or (now_datetime() if status == "Withdrawn" else None),
		"expires_on": values.get("expires_on") or None,
		"evidence": _clean(values.get("evidence"), 2000),
	})
	if doc.channel and not frappe.db.exists("VerityAI Growth Channel", doc.channel):
		frappe.throw("Growth channel was not found.", frappe.DoesNotExistError)
	return doc.insert(ignore_permissions=True)


def suppress(identifier, reason, channel=None, expires_on=None, source="Operator console"):
	if channel and not frappe.db.exists("VerityAI Growth Channel", channel):
		frappe.throw("Growth channel was not found.", frappe.DoesNotExistError)
	digest = _identity_hash(identifier)
	for existing in frappe.get_all(
		"VerityAI Suppression Record",
		filters={"identity_hash": digest, "channel": channel, "status": "Active"},
		fields=["name", "expires_on"],
		order_by="starts_on desc",
	):
		if not existing.expires_on or get_datetime(existing.expires_on) >= now_datetime():
			return frappe.get_doc("VerityAI Suppression Record", existing.name)
		frappe.db.set_value("VerityAI Suppression Record", existing.name, "status", "Expired", update_modified=False)
	return frappe.get_doc({
		"doctype": "VerityAI Suppression Record",
		"identity_hash": digest,
		"channel": channel,
		"reason": _required(reason, "Suppression reason", 500),
		"source": _clean(source),
		"starts_on": now_datetime(),
		"expires_on": expires_on or None,
		"status": "Active",
	}).insert(ignore_permissions=True)


def lift_suppression(record):
	if not frappe.db.exists("VerityAI Suppression Record", record):
		frappe.throw("Suppression record was not found.", frappe.DoesNotExistError)
	doc = frappe.get_doc("VerityAI Suppression Record", record)
	if doc.status == "Active":
		doc.status = "Lifted"
		doc.save(ignore_permissions=True)
	return doc


def is_suppressed(identifier, channel=None, at_time=None):
	digest = _identity_hash(identifier)
	at_time = get_datetime(at_time or now_datetime())
	rows = frappe.get_all("VerityAI Suppression Record", filters={"identity_hash": digest, "status": "Active"}, fields=["name", "channel", "expires_on"])
	for row in rows:
		if row.channel and row.channel != channel:
			continue
		if not row.expires_on or get_datetime(row.expires_on) >= at_time:
			return True
	return False


def protect_event_update(doc, method=None):
	if not doc.is_new():
		frappe.throw("Growth events are immutable.", frappe.PermissionError)


def protect_event_delete(doc, method=None):
	frappe.throw("Growth events cannot be deleted.", frappe.PermissionError)


def channel_funnel():
	channels = frappe.get_all(
		"VerityAI Growth Channel",
		filters={"channel_code": ["in", ["WIDGET", "WHATSAPP"]]},
		fields=["name", "channel_code", "channel_name"],
	)
	rows = {
		channel.name: {
			"channel": channel.name,
			"channel_code": channel.channel_code,
			"channel_name": channel.channel_name,
			"inbound_messages": 0,
			"conversations": 0,
			"leads": 0,
			"qualified_leads": 0,
			"opportunities": 0,
			"won": 0,
			"won_value": 0,
		}
		for channel in channels
	}
	events = frappe.get_all(
		"VerityAI Growth Event",
		filters={"channel": ["in", list(rows)]},
		fields=["channel", "event_type", "metadata"],
		limit_page_length=0,
	) if rows else []
	field_by_event = {
		"channel.inbound_received": "inbound_messages",
		"conversation.started": "conversations",
		"lead.captured": "leads",
		"lead.qualified": "qualified_leads",
		"opportunity.created": "opportunities",
		"opportunity.won": "won",
	}
	for event in events:
		fieldname = field_by_event.get(event.event_type)
		if not fieldname:
			continue
		rows[event.channel][fieldname] += 1
		if event.event_type == "opportunity.won":
			try:
				metadata = json.loads(event.metadata or "{}")
			except (TypeError, ValueError):
				metadata = {}
			rows[event.channel]["won_value"] += flt(metadata.get("amount"))
	for row in rows.values():
		row["lead_conversion_rate"] = min(100, round(row["leads"] / row["conversations"] * 100, 1)) if row["conversations"] else 0
		row["win_rate"] = min(100, round(row["won"] / row["opportunities"] * 100, 1)) if row["opportunities"] else 0
	return sorted(rows.values(), key=lambda row: row["channel_code"])


def summary():
	channels = frappe.get_all("VerityAI Growth Channel", fields=[
		"name", "channel_name", "channel_code", "channel_type", "delivery_mode", "risk_class", "status",
		"owner_user", "adapter", "allowed_actions", "monthly_limit", "notes", "modified",
	], order_by="status asc, channel_name asc", limit_page_length=250)
	campaigns = frappe.get_all("VerityAI Growth Campaign", fields=[
		"name", "campaign_name", "campaign_code", "channel", "objective", "audience", "source", "medium",
		"content", "term", "starts_on", "ends_on", "budget", "currency", "delivery_limit", "owner_user",
		"status", "notes", "modified",
	], order_by="modified desc", limit_page_length=250)
	suppressions = frappe.get_all("VerityAI Suppression Record", fields=[
		"name", "identity_hash", "channel", "reason", "source", "starts_on", "expires_on", "status",
	], order_by="starts_on desc", limit_page_length=100)
	current_time = now_datetime()
	for row in suppressions:
		if row.status == "Active" and row.expires_on and get_datetime(row.expires_on) < current_time:
			row.status = "Expired"
	return {
		"feature_flags": feature_flags(),
		"channels": channels,
		"campaigns": campaigns,
		"channel_funnel": channel_funnel(),
		"metrics": {
			"active_channels": sum(row.status == "Active" for row in channels),
			"active_campaigns": sum(row.status == "Active" for row in campaigns),
			"events": frappe.db.count("VerityAI Growth Event"),
			"active_suppressions": sum(row.status == "Active" for row in suppressions),
		},
		"recent_events": frappe.get_all("VerityAI Growth Event", fields=[
			"name", "event_type", "occurred_at", "channel", "campaign", "workspace", "source", "medium", "correlation_id",
		], order_by="occurred_at desc", limit_page_length=50),
		"recent_consents": frappe.get_all("VerityAI Consent Record", fields=[
			"name", "subject_type", "subject_hash", "purpose", "channel", "status", "source", "captured_on", "expires_on",
		], order_by="captured_on desc", limit_page_length=50),
		"suppressions": suppressions,
	}
