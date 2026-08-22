import json
import uuid

import frappe


def run():
	import uuid

	from verity_ai.engine.openai_handler import process_chat
	from verity_ai.engine.tools import search_knowledge_base
	from verity_ai.entitlements import EntitlementDenied
	from verityai_saas.services.ingestion import crawl_url

	tenant = None
	for row in frappe.get_all("AI Configuration", fields=["name", "tenant"], order_by="modified desc", limit=100):
		if not row.tenant or not frappe.db.get_value("AI Tenant", row.tenant, "active"):
			continue
		config = frappe.get_doc("AI Configuration", row.name)
		if config.get_password("provider_api_key", raise_exception=False) or config.get_password("openai_api_key", raise_exception=False):
			tenant = row.tenant
			break
	if not tenant:
		return {"success": False, "error": "No active local tenant with an AI provider key was found."}
	content, pages, size = crawl_url("https://veritycore.co.zw", max_pages=5)
	frappe.db.savepoint("verity_live_verification")
	source = None
	try:
		source = frappe.get_doc({
			"doctype": "AI Knowledge Source",
			"tenant": tenant,
			"title": "VerityCore live website verification",
			"content": content,
			"active": 1,
		}).insert(ignore_permissions=True)
		retrieved = search_knowledge_base(tenant, "What services and business solutions does VerityCore provide?", limit=4)
		chat_status = "passed"
		try:
			chat_reply = process_chat(
				tenant_name=tenant,
				session_id=f"production-verification-{uuid.uuid4()}",
				message="In two short sentences, what business solutions does VerityCore provide?",
				platform="Web",
			)
		except EntitlementDenied as exc:
			chat_status = "blocked_by_entitlement"
			chat_reply = str(exc)
		return {
			"success": True,
			"tenant": tenant,
			"website_pages": pages,
			"website_bytes": size,
			"source": source.name,
			"chunks": frappe.db.count("AI Knowledge Chunk", {"knowledge_source": source.name}),
			"retrieval_found_veritycore": "veritycore" in (retrieved or "").lower(),
			"retrieval_length": len(retrieved or ""),
			"chat_status": chat_status,
			"assistant_reply": str(chat_reply or "")[:800],
		}
	finally:
		frappe.db.rollback(save_point="verity_live_verification")
