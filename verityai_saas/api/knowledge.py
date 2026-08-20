import hashlib

import frappe

from verityai_saas.api._response import endpoint, json_value
from verityai_saas.services import engine, ingestion
from verityai_saas.services.onboarding import set_step
from verityai_saas.services.permissions import check_workspace_access, require_workspace_permission


@frappe.whitelist()
@endpoint
def list_sources(workspace):
	check_workspace_access(workspace)
	return engine.list_knowledge_sources(workspace)


@frappe.whitelist()
@endpoint
def ingestion_status(workspace):
	check_workspace_access(workspace)
	return ingestion.list_ingestions(workspace)


@frappe.whitelist()
@endpoint
def detail(workspace, source):
	require_workspace_permission(workspace, "manage_knowledge")
	return engine.get_knowledge_source(workspace, source)


@frappe.whitelist(methods=["POST"])
@endpoint
def create(workspace, title, content=None, file=None):
	require_workspace_permission(workspace, "manage_knowledge")
	if file:
		name = ingestion.queue_ingestion(workspace, title, "File", file_name=file)
		set_step(workspace, "knowledge")
		return {"ingestion": name, "status": "Pending"}
	if not (content or "").strip():
		frappe.throw("Knowledge content is required.", frappe.ValidationError)
	name = engine.create_knowledge_source(workspace, title, content)
	frappe.get_doc({
		"doctype": "VerityAI Knowledge Ingestion", "workspace": workspace, "knowledge_source": name,
		"title": title, "source_type": "Text", "status": "Ready",
		"content_hash": hashlib.sha256(content.encode("utf-8")).hexdigest(),
		"bytes_processed": len(content.encode("utf-8")), "pages_processed": 1,
		"last_refreshed_on": frappe.utils.now_datetime(),
	}).insert(ignore_permissions=True)
	set_step(workspace, "knowledge")
	return {"source": name, "status": "Ready"}


@frappe.whitelist(methods=["POST"])
@endpoint
def ingest_file(workspace, title, file):
	require_workspace_permission(workspace, "manage_knowledge")
	name = ingestion.queue_ingestion(workspace, title, "File", file_name=file)
	set_step(workspace, "knowledge")
	return {"ingestion": name, "status": "Pending"}


@frappe.whitelist(methods=["POST"])
@endpoint
def ingest_url(workspace, title, url):
	require_workspace_permission(workspace, "manage_knowledge")
	name = ingestion.queue_ingestion(workspace, title, "URL", source_url=url)
	set_step(workspace, "knowledge")
	return {"ingestion": name, "status": "Pending"}


@frappe.whitelist(methods=["POST"])
@endpoint
def refresh(workspace, ingestion_name):
	require_workspace_permission(workspace, "manage_knowledge")
	return {"ingestion": ingestion.refresh_ingestion(workspace, ingestion_name), "status": "Pending"}


@frappe.whitelist(methods=["POST"])
@endpoint
def update_processing(workspace, ingestion_name, values):
	require_workspace_permission(workspace, "manage_knowledge")
	return ingestion.update_ingestion(workspace, ingestion_name, json_value(values, {}))


@frappe.whitelist(methods=["POST"])
@endpoint
def delete_processing(workspace, ingestion_name):
	require_workspace_permission(workspace, "manage_knowledge")
	return ingestion.delete_ingestion(workspace, ingestion_name)


@frappe.whitelist(methods=["POST"])
@endpoint
def update(workspace, source, values):
	require_workspace_permission(workspace, "manage_knowledge")
	return {"source": engine.update_knowledge_source(workspace, source, json_value(values, {}))}


@frappe.whitelist(methods=["POST"])
@endpoint
def delete(workspace, source):
	require_workspace_permission(workspace, "manage_knowledge")
	return engine.delete_knowledge_source(workspace, source)
