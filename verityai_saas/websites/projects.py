import re

import frappe
from frappe.utils import cint, now_datetime

from verityai_saas.services import growth
from verityai_saas.websites.definitions import SCHEMA_VERSION, canonical_json, definition_hash, validate_definition


PROJECT_STATUSES = {"Draft", "Ready", "Published", "Archived"}
PROJECT_TRANSITIONS = {"Draft": {"Ready", "Archived"}, "Ready": {"Draft", "Archived"}, "Archived": {"Draft"}}
PROJECT_SLUG_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
TEMPLATE_KEY_PATTERN = re.compile(r"^[a-z0-9]+(?:[._-][a-z0-9]+)*$")
RESERVED_SUBDOMAINS = {"admin", "api", "app", "assets", "billing", "dashboard", "docs", "help", "login", "mail", "support", "www"}


def _clean(value, label, maximum=140, required=False):
	value = str(value or "").strip()
	if required and not value:
		frappe.throw(f"{label} is required.", frappe.ValidationError)
	if len(value) > maximum:
		frappe.throw(f"{label} cannot exceed {maximum} characters.", frappe.ValidationError)
	return value


def normalize_slug(value):
	value = _clean(value, "Project slug", 63, required=True).lower()
	if not PROJECT_SLUG_PATTERN.fullmatch(value) or value in RESERVED_SUBDOMAINS:
		frappe.throw("Project slug is invalid or reserved.", frappe.ValidationError)
	return value


def require_builder_enabled():
	if not growth.feature_flags().get("website_builder_enabled"):
		frappe.throw("Website projects are not enabled for customers yet.", frappe.PermissionError)


def _workspace_context(workspace):
	row = frappe.db.get_value("VerityAI Workspace", workspace, ["name", "account", "business_name"], as_dict=True)
	if not row:
		frappe.throw("Workspace was not found.", frappe.DoesNotExistError)
	return row


def _scoped_project(workspace, project):
	name = frappe.db.get_value("VerityAI Website Project", {"name": project, "workspace": workspace}, "name")
	if not name:
		frappe.throw("Website project was not found in this workspace.", frappe.DoesNotExistError)
	return frappe.get_doc("VerityAI Website Project", name)


def _account_has_active_project(account, exclude=None):
	workspaces = frappe.get_all("VerityAI Workspace", filters={"account": account}, pluck="name")
	filters = {"workspace": ["in", workspaces], "status": ["!=", "Archived"]}
	if exclude:
		filters["name"] = ["!=", exclude]
	return bool(workspaces and frappe.db.exists("VerityAI Website Project", filters))


def project_data(doc, include_definition=False):
	data = {key: doc.get(key) for key in (
		"name", "workspace", "project_name", "project_slug", "business_name", "template_key", "status",
		"current_version", "published_version", "verity_subdomain", "custom_domain", "domain_status",
		"widget_enabled", "whatsapp_enabled", "crm_enabled", "created_by_user", "creation", "modified",
	)}
	data["version_count"] = frappe.db.count("VerityAI Website Definition Version", {"project": doc.name})
	if include_definition and doc.current_version:
		version = frappe.get_doc("VerityAI Website Definition Version", doc.current_version)
		data["definition"] = frappe.parse_json(version.definition_json)
		data["definition_version"] = version.version_number
		data["definition_hash"] = version.definition_hash
	return data


def list_projects(workspace):
	_workspace_context(workspace)
	rows = frappe.get_all("VerityAI Website Project", filters={"workspace": workspace}, pluck="name", order_by="modified desc")
	return [project_data(frappe.get_doc("VerityAI Website Project", name)) for name in rows]


def get_project(workspace, project):
	return project_data(_scoped_project(workspace, project), include_definition=True)


def create_project(workspace, values, user=None):
	require_builder_enabled()
	values = values or {}
	context = _workspace_context(workspace)
	if _account_has_active_project(context.account):
		frappe.throw("The free website allowance is one active project per account.", frappe.ValidationError)
	doc = frappe.get_doc({
		"doctype": "VerityAI Website Project",
		"workspace": workspace,
		"project_name": _clean(values.get("project_name"), "Project name", required=True),
		"project_slug": normalize_slug(values.get("project_slug")),
		"business_name": _clean(values.get("business_name") or context.business_name, "Business name", required=True),
		"template_key": _clean(values.get("template_key") or "starter-v1", "Template key", 80, required=True),
		"status": "Draft",
		"verity_subdomain": normalize_slug(values.get("project_slug")),
		"domain_status": "Unconfigured",
		"widget_enabled": cint(values.get("widget_enabled")),
		"whatsapp_enabled": cint(values.get("whatsapp_enabled")),
		"crm_enabled": 1 if values.get("crm_enabled") is None else cint(values.get("crm_enabled")),
		"created_by_user": user or frappe.session.user,
	}).insert(ignore_permissions=True)
	_record_project_event("website.project_created", doc)
	if values.get("definition"):
		add_definition_version(workspace, doc.name, values.get("definition"), source=values.get("source") or "Manual", user=user)
	return get_project(workspace, doc.name)


def update_project(workspace, project, values):
	require_builder_enabled()
	doc = _scoped_project(workspace, project)
	if doc.status == "Archived":
		frappe.throw("Restore the website project before editing it.", frappe.ValidationError)
	values = values or {}
	for fieldname, label, maximum in (("project_name", "Project name", 140), ("business_name", "Business name", 140), ("template_key", "Template key", 80)):
		if fieldname in values:
			doc.set(fieldname, _clean(values.get(fieldname), label, maximum, required=True))
	for fieldname in ("widget_enabled", "whatsapp_enabled", "crm_enabled"):
		if fieldname in values:
			doc.set(fieldname, cint(values.get(fieldname)))
	doc.save(ignore_permissions=True)
	_record_project_event("website.project_updated", doc)
	return get_project(workspace, doc.name)


def add_definition_version(workspace, project, definition, source="Manual", user=None):
	require_builder_enabled()
	doc = _scoped_project(workspace, project)
	if doc.status == "Archived":
		frappe.throw("Restore the website project before adding a version.", frappe.ValidationError)
	normalized = validate_definition(definition)
	payload = canonical_json(normalized)
	digest = definition_hash(payload)
	existing = frappe.db.get_value("VerityAI Website Definition Version", {"project": doc.name, "definition_hash": digest}, "name")
	if existing:
		return version_data(frappe.get_doc("VerityAI Website Definition Version", existing), include_definition=True)
	latest = frappe.db.get_value("VerityAI Website Definition Version", {"project": doc.name}, "max(version_number)") or 0
	version = frappe.get_doc({
		"doctype": "VerityAI Website Definition Version", "workspace": workspace, "project": doc.name,
		"version_number": cint(latest) + 1, "schema_version": SCHEMA_VERSION, "status": "Validated",
		"source": source if source in {"Manual", "Website Doctor", "AI Generation", "Import"} else "Manual",
		"definition_json": payload, "definition_hash": digest,
		"created_by_user": user or frappe.session.user, "validated_on": now_datetime(),
	}).insert(ignore_permissions=True)
	doc.current_version = version.name
	doc.save(ignore_permissions=True)
	_record_project_event("website.definition_version_created", doc, version)
	return version_data(version, include_definition=True)


def version_data(doc, include_definition=False):
	data = {key: doc.get(key) for key in (
		"name", "workspace", "project", "version_number", "schema_version", "status", "source",
		"definition_hash", "created_by_user", "validated_on", "creation",
	)}
	if include_definition:
		data["definition"] = frappe.parse_json(doc.definition_json)
	return data


def set_current_version(workspace, project, version):
	require_builder_enabled()
	doc = _scoped_project(workspace, project)
	version_name = frappe.db.get_value("VerityAI Website Definition Version", {"name": version, "workspace": workspace, "project": doc.name}, "name")
	if not version_name:
		frappe.throw("Website definition version was not found in this project.", frappe.DoesNotExistError)
	if doc.current_version == version_name:
		return get_project(workspace, doc.name)
	doc.current_version = version_name
	doc.save(ignore_permissions=True)
	_record_project_event("website.current_version_changed", doc, frappe.get_doc("VerityAI Website Definition Version", version_name))
	return get_project(workspace, doc.name)


def set_status(workspace, project, status):
	require_builder_enabled()
	doc = _scoped_project(workspace, project)
	status = _clean(status, "Project status", 20, required=True).title()
	if status == "Published":
		frappe.throw("Publishing is unavailable until the deployment and rollback gate passes.", frappe.ValidationError)
	if status not in PROJECT_STATUSES or status not in PROJECT_TRANSITIONS.get(doc.status, set()):
		frappe.throw(f"Website project cannot move from {doc.status} to {status}.", frappe.ValidationError)
	if status == "Ready" and not doc.current_version:
		frappe.throw("Add a validated website definition before marking the project ready.", frappe.ValidationError)
	doc.status = status
	doc.save(ignore_permissions=True)
	_record_project_event(f"website.project_{status.lower()}", doc)
	return project_data(doc)


def validate_project_document(doc, method=None):
	context = _workspace_context(doc.workspace)
	doc.project_slug = normalize_slug(doc.project_slug)
	doc.verity_subdomain = doc.verity_subdomain or doc.project_slug
	doc.created_by_user = doc.created_by_user or frappe.session.user
	doc.template_key = _clean(doc.template_key, "Template key", 80, required=True).lower()
	if not TEMPLATE_KEY_PATTERN.fullmatch(doc.template_key):
		frappe.throw("Template key contains unsupported characters.", frappe.ValidationError)
	if doc.verity_subdomain and doc.verity_subdomain != doc.project_slug:
		frappe.throw("The reserved Verity subdomain must match the immutable project slug.", frappe.ValidationError)
	if doc.custom_domain or doc.published_version or doc.status == "Published":
		frappe.throw("Domains and publishing require the later deployment security gate.", frappe.ValidationError)
	if doc.current_version and not frappe.db.exists("VerityAI Website Definition Version", {"name": doc.current_version, "workspace": doc.workspace, "project": doc.name}):
		frappe.throw("Current version must belong to this website project.", frappe.ValidationError)
	previous = doc.get_doc_before_save()
	if doc.status == "Ready" and not doc.current_version:
		frappe.throw("A ready website project requires a validated current version.", frappe.ValidationError)
	if previous and previous.status != doc.status and doc.status not in PROJECT_TRANSITIONS.get(previous.status, set()):
		frappe.throw(f"Website project cannot move from {previous.status} to {doc.status}.", frappe.ValidationError)
	if (doc.is_new() or (previous and previous.status == "Archived" and doc.status != "Archived")) and _account_has_active_project(context.account, exclude=doc.name):
		frappe.throw("The free website allowance is one active project per account.", frappe.ValidationError)
	if previous and previous.project_slug != doc.project_slug:
		frappe.throw("Project slug cannot change after reservation.", frappe.ValidationError)


def validate_definition_document(doc, method=None):
	project = frappe.db.get_value("VerityAI Website Project", doc.project, ["workspace", "name"], as_dict=True)
	if not project or project.workspace != doc.workspace:
		frappe.throw("Website definition version must belong to the same workspace as its project.", frappe.ValidationError)
	payload = canonical_json(doc.definition_json)
	doc.definition_json = payload
	doc.definition_hash = definition_hash(payload)
	doc.schema_version = SCHEMA_VERSION
	doc.created_by_user = doc.created_by_user or frappe.session.user
	doc.validated_on = doc.validated_on or now_datetime()
	if cint(doc.version_number) < 1 or doc.status != "Validated":
		frappe.throw("Website definition versions must be validated positive versions.", frappe.ValidationError)
	duplicate = frappe.db.get_value("VerityAI Website Definition Version", {"project": doc.project, "version_number": doc.version_number}, "name")
	if duplicate and duplicate != doc.name:
		frappe.throw("Website definition version number already exists for this project.", frappe.DuplicateEntryError)
	duplicate_hash = frappe.db.get_value("VerityAI Website Definition Version", {"project": doc.project, "definition_hash": doc.definition_hash}, "name")
	if duplicate_hash and duplicate_hash != doc.name:
		frappe.throw("This website definition already exists in the project.", frappe.DuplicateEntryError)


def protect_definition_update(doc, method=None):
	if not doc.is_new():
		frappe.throw("Website definition versions are immutable.", frappe.PermissionError)


def protect_definition_delete(doc, method=None):
	frappe.throw("Website definition versions cannot be deleted.", frappe.PermissionError)


def protect_project_delete(doc, method=None):
	frappe.throw("Website projects are archived instead of deleted.", frappe.PermissionError)


def _record_project_event(event_type, project, version=None):
	if not growth._tracking_available():
		return
	context = growth._workspace_context(workspace=project.workspace)
	channel = frappe.db.get_value("VerityAI Growth Channel", {"channel_code": "WEBSITE"}, "name")
	if context and channel:
		growth.record_lifecycle_event(
			event_type, workspace=context.name, account=context.account, channel=channel, source="website_builder",
			object_type="VerityAI Website Definition Version" if version else "VerityAI Website Project",
			object_name=version.name if version else project.name, correlation_id=project.name,
			idempotency_key=f"{event_type}:{version.name if version else project.name}:{project.modified}",
			metadata={"project_status": project.status, "version": cint(version.version_number) if version else None},
		)
