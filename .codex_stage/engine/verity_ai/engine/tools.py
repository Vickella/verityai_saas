import io
import html
import csv
import json
import re

import frappe
import requests

from verity_ai.action_registry import APPROVER_ROLES, BLOCKED_WRITE_DOCTYPES, SENSITIVE_ACTIONS, action_risk, configured_blocked_doctypes
from verity_ai.tenant_security import mask_sensitive_text


LEGACY_ENTERPRISE_BLOCKED_ACTION_DOCTYPES = {
	"User",
	"Role",
	"Role Profile",
	"DocType",
	"Custom Field",
	"Property Setter",
	"System Settings",
	"Installed Applications",
	"Integration Request",
	"OAuth Client",
	"OAuth Bearer Token",
	"API Key",
	"Social Login Key",
	"Email Account",
	"Email Domain",
	"Print Format",
	"Server Script",
	"Client Script",
}

SENSITIVE_DOCUMENT_ACTIONS = SENSITIVE_ACTIONS
AI_ACTION_APPROVER_ROLES = APPROVER_ROLES

DEFAULT_ALLOWED_DESK_DOCTYPES = {
	"Customer",
	"Supplier",
	"Item",
	"Item Price",
	"Sales Order",
	"Sales Invoice",
	"Quotation",
	"Lead",
	"Opportunity",
	"Project",
	"Task",
	"Stock Entry",
	"Purchase Order",
	"Purchase Invoice",
	"Employee",
	"Salary Slip",
}


def safe_tool_error(error):
	return mask_sensitive_text(error, max_length=1000)


def first_handled_hook(hook_name, **kwargs):
	for method in frappe.get_hooks(hook_name):
		result = frappe.get_attr(method)(**kwargs)
		if result and result.get("handled"):
			return result
	return None


def commerce_capabilities(tenant_name):
	try:
		result = first_handled_hook("verity_ai_commerce_capability_handler", tenant_name=tenant_name)
		return result or {}
	except Exception:
		return {}

def session_platform(session_name):
	if session_name and frappe.db.exists("DocType", "AI Chat Session"):
		return frappe.db.get_value("AI Chat Session", session_name, "platform")
	return None

def capture_lead(
	tenant_name,
	session_name,
	name,
	email=None,
	phone=None,
	business_type=None,
	location=None,
	enquiry_type=None,
	current_system=None,
	problems_faced=None,
	requirements=None,
	appointment_requested=None,
	appointment_date=None,
	appointment_time=None,
	appointment_mode=None,
	appointment_notes=None,
	extra_details=None,
):
	try:
		source_channel = session_platform(session_name)
		filters = {"tenant": tenant_name, "lead_name": name}
		if email:
			filters = {"tenant": tenant_name, "email": email}
		existing = frappe.get_all("AI Lead", filters=filters, fields=["name"], limit=1, ignore_permissions=True)
		if existing:
			doc = frappe.get_doc("AI Lead", existing[0].get("name"))
		else:
			doc = frappe.get_doc({"doctype": "AI Lead", "lead_name": name, "tenant": tenant_name, "chat_session": session_name, "status": "New"})

		updates = {
			"email": email,
			"phone": phone,
			"business_type": business_type,
			"location": location,
			"enquiry_type": enquiry_type,
			"current_system": current_system,
			"problems_faced": problems_faced,
			"requirements": requirements,
			"appointment_requested": appointment_requested,
			"appointment_date": appointment_date,
			"appointment_time": appointment_time,
			"appointment_mode": appointment_mode,
			"appointment_notes": appointment_notes,
			"dynamic_details": json.dumps(extra_details or {}, default=str) if extra_details else None,
			"chat_session": session_name,
			"source_channel": source_channel,
		}
		for field, value in updates.items():
			if value is not None and value != "" and hasattr(doc, field):
				setattr(doc, field, value)
		if doc.get("__islocal"):
			doc.insert(ignore_permissions=True)
		else:
			doc.save(ignore_permissions=True)
		integration = first_handled_hook(
			"verity_ai_lead_capture_handler",
			tenant_name=tenant_name,
			lead=doc.name,
			name=name,
			email=email,
			phone=phone,
			appointment_requested=appointment_requested,
			appointment_date=appointment_date,
			appointment_time=appointment_time,
			appointment_mode=appointment_mode,
			appointment_notes=appointment_notes,
			source_channel=source_channel,
		)
		customer_id = integration.get("customer") if integration else None
		if not integration and name and (email or phone) and frappe.db.exists("DocType", "Customer"):
			from verity_ai.sales.quotation_flow import ensure_customer

			customer_id = ensure_customer(name, email=email, phone=phone)
			if hasattr(doc, "customer"):
				doc.customer = customer_id
				doc.save(ignore_permissions=True)
		frappe.db.commit()
		return json.dumps({
			"success": True,
			"message": "Lead captured successfully.",
			"lead_id": doc.name,
			"customer": customer_id,
			"appointment": integration.get("appointment") if integration else None,
		}, default=str)
	except Exception as e:
		return json.dumps({"success": False, "error": safe_tool_error(e)})

def get_tenant_business_nature(tenant_name):
	if not tenant_name or not frappe.db.exists("DocType", "AI Tenant"):
		return None
	return frappe.db.get_value("AI Tenant", tenant_name, "business_nature")


def get_lead_capture_schema(tenant_name):
	try:
		business_nature = get_tenant_business_nature(tenant_name)
		if not business_nature or not frappe.db.exists("AI Business Nature", business_nature):
			return json.dumps({
				"success": True,
				"assistant_owner_business_nature": business_nature,
				"fields": [],
				"usage": "These are the assistant owner's internal sales discovery fields. They do not describe the visitor or prospect.",
			})
		doc = frappe.get_doc("AI Business Nature", business_nature)
		fields = []
		for row in doc.get("lead_fields", []):
			fields.append(
				{
					"fieldname": row.fieldname,
					"label": row.label,
					"fieldtype": row.fieldtype,
					"required": bool(row.required),
					"options": row.options,
					"description": row.description,
				}
			)
		return json.dumps({
			"success": True,
			"assistant_owner_business_nature": business_nature,
			"fields": fields,
			"usage": (
				"Use these fields to qualify a buyer for the organisation operating this assistant. "
				"Never call this the visitor's business nature and never infer the visitor's industry from it. "
				"If the visitor's industry matters, ask for it separately and store it as a prospect detail."
			),
		}, default=str)
	except Exception as e:
		return json.dumps({"success": False, "error": safe_tool_error(e)})
def format_knowledge_result(row):
	title = row.get("title") or "Knowledge"
	chunk = row.get("chunk_index")
	source = row.get("source") or title
	label = f"{title}"
	if chunk:
		label = f"{label} (chunk {chunk})"
	content = (row.get("content") or "")[:1200]
	return f"Source: {label}\nReference: {source}\n{content}"


def search_source_fallback(tenant_name, query, limit=4):
	if not frappe.db.exists("DocType", "AI Knowledge Source"):
		return []
	words = [word.lower() for word in re.findall(r"[a-zA-Z0-9]{3,}", query or "")][:12]
	rows = frappe.get_all(
		"AI Knowledge Source",
		filters={"tenant": tenant_name, "active": 1},
		fields=["name", "title", "content", "summary"],
		limit=50,
		ignore_permissions=True,
	)
	scored = []
	for row in rows:
		content = (row.get("content") or row.get("summary") or "")[:8000]
		text = f"{row.get('title') or ''}\n{content}".lower()
		score = sum(text.count(word) for word in words)
		if score:
			scored.append({"score": score, "source": row.get("name"), "title": row.get("title") or "Knowledge", "content": content})
	scored.sort(reverse=True, key=lambda item: item["score"])
	return scored[: int(limit or 4)]


def search_knowledge_base(tenant_name, query, limit=4):
	if not tenant_name or not query:
		return ""
	try:
		from verity_ai.knowledge_index import search_knowledge_chunks

		results = search_knowledge_chunks(tenant_name, query, limit=limit)
	except Exception:
		results = []
	if not results:
		results = search_source_fallback(tenant_name, query, limit=limit)
	return "\n\n".join(format_knowledge_result(row) for row in results)

def get_item_price(config, item_code):
	try:
		handled = first_handled_hook("verity_ai_item_price_handler", tenant_name=config.tenant, item_code=item_code)
		if handled:
			return json.dumps({key: value for key, value in handled.items() if key != "handled"}, default=str)
		if config.erpnext_url and config.erpnext_api_key and config.erpnext_api_secret:
			url = f"{config.erpnext_url}/api/method/erpnext.stock.get_item_details.get_item_details"
			headers = {"Authorization": f"token {config.get_password('erpnext_api_key')}:{config.get_password('erpnext_api_secret')}"}
			params = {"item_code": item_code, "company": frappe.defaults.get_user_default("Company") or "Default"}
			response = requests.get(url, headers=headers, params=params, timeout=20)

			if response.status_code == 200:
				data = response.json().get("message", {})
				price = data.get("price_list_rate", 0)
				return json.dumps({"success": True, "item_code": item_code, "public_selling_price": price})
			return json.dumps({"success": False, "error": "Could not fetch public selling price from ERPNext."})

		if frappe.db.exists("Item", item_code):
			price_list_rate = frappe.db.get_value("Item Price", {"item_code": item_code}, "price_list_rate")
			return json.dumps({"success": True, "item_code": item_code, "public_selling_price": price_list_rate or 0})
		return json.dumps({"success": False, "error": f"Item {item_code} not found."})
	except Exception as e:
		return json.dumps({"success": False, "error": safe_tool_error(e)})


def search_product_catalog(config, query=None, limit=10):
	try:
		handled = first_handled_hook(
			"verity_ai_catalog_search_handler",
			tenant_name=config.tenant,
			query=query,
			limit=min(max(int(limit or 10), 1), 25),
		)
		if handled:
			return json.dumps({key: value for key, value in handled.items() if key != "handled"}, default=str)
		return json.dumps({"success": False, "error": "Product catalogue search is not available for this tenant."})
	except Exception as e:
		return json.dumps({"success": False, "error": safe_tool_error(e)})


def manage_native_sales(tenant_name, user, action, reference=None, status=None, values=None, filters=None, limit=50):
	try:
		handled = first_handled_hook(
			"verity_ai_sales_crm_handler",
			tenant_name=tenant_name,
			user=user,
			action=action,
			reference=reference,
			status=status,
			values=values or {},
			filters=filters or {},
			limit=min(max(int(limit or 50), 1), 200),
		)
		if handled:
			return json.dumps({key: value for key, value in handled.items() if key != "handled"}, default=str)
		return json.dumps({"success": False, "error": "Tenant-native sales CRM is not available."})
	except Exception as e:
		return json.dumps({"success": False, "error": safe_tool_error(e)})

def create_service_item(item_code, rate=None):
	try:
		from verity_ai.sales.quotation_flow import ensure_service_item

		item = ensure_service_item(item_code, rate=rate)
		frappe.db.commit()
		return json.dumps({"success": True, "item_code": item, "message": "Service item is ready for quotations."})
	except Exception as e:
		frappe.db.rollback()
		return json.dumps({"success": False, "error": safe_tool_error(e)})


def request_quotation_approval(config, customer, items, tenant_name=None, client_whatsapp_number="", client_email=None, notes=None, estimated_total=None, create_missing_items=False, chat_session=None, source_channel=None):
	try:
		handled = first_handled_hook(
			"verity_ai_quotation_request_handler",
			tenant_name=tenant_name or config.tenant,
			customer=customer,
			items=items,
			client_whatsapp_number=client_whatsapp_number,
			client_email=client_email,
			notes=notes,
			chat_session=chat_session,
			source_channel=source_channel,
		)
		if handled:
			frappe.db.commit()
			return json.dumps({key: value for key, value in handled.items() if key != "handled"}, default=str)
		from verity_ai.sales.quotation_flow import prepare_quotation_request

		doc = prepare_quotation_request(
			config,
			customer,
			items,
			tenant_name=tenant_name,
			client_whatsapp_number=client_whatsapp_number,
			client_email=client_email,
			notes=notes,
			estimated_total=estimated_total,
			create_missing_items=create_missing_items,
			chat_session=chat_session,
			source_channel=source_channel,
		)
		frappe.db.commit()

		admin_whatsapp = getattr(config, "admin_whatsapp_number", None)
		if admin_whatsapp:
			from verity_ai.api.whatsapp import send_whatsapp_message

			msg = f"New quotation request {doc.name} for {customer}. Draft quotation: {doc.erpnext_quotation_id}. Quotation total: {doc.estimated_total or 'Not set'}. Reply 'Approve {doc.name}' or approve it in VerityPack to send it."
			send_whatsapp_message(config.whatsapp_phone_id, admin_whatsapp, msg, config=config)

		return json.dumps({"success": True, "quotation_request": doc.name, "quotation": doc.erpnext_quotation_id, "estimated_total": doc.estimated_total, "message": "Quotation request staged for review. The quotation request is pending approval."})
	except Exception as e:
		return json.dumps({"success": False, "error": safe_tool_error(e)})


def check_quote_status(tenant_name, quotation_reference=None, customer=None, client_email=None, client_whatsapp_number=None):
	try:
		handled = first_handled_hook(
			"verity_ai_quote_status_handler",
			tenant_name=tenant_name,
			quotation_reference=quotation_reference,
			customer=customer,
			client_email=client_email,
			client_whatsapp_number=client_whatsapp_number,
		)
		if handled:
			return json.dumps({key: value for key, value in handled.items() if key != "handled"}, default=str)
		from verity_ai.sales.quotation_flow import public_quote_status

		return json.dumps(
			public_quote_status(
				tenant_name,
				quotation_reference=quotation_reference,
				customer=customer,
				client_email=client_email,
				client_whatsapp_number=client_whatsapp_number,
			),
			default=str,
		)
	except Exception as e:
		return json.dumps({"success": False, "error": safe_tool_error(e)})


def request_human_handoff(config, session, reason, estimated_value=None):
	try:
		session.status = "Human Handoff"
		if estimated_value is not None:
			session.estimated_deal_value = estimated_value
		session.save(ignore_permissions=True)

		admin_whatsapp = getattr(config, "admin_whatsapp_number", None)
		if admin_whatsapp:
			from verity_ai.api.whatsapp import send_whatsapp_message

			msg = f"Human handoff requested for session {session.session_id}. Reason: {reason}. Estimated value: {estimated_value or 'Not set'}."
			send_whatsapp_message(config.whatsapp_phone_id, admin_whatsapp, msg, config=config)

		return json.dumps({"success": True, "message": "A senior team member has been notified."})
	except Exception as e:
		return json.dumps({"success": False, "error": safe_tool_error(e)})


def allowed_desk_doctypes(config):
	configured = (config.get("erpnext_assistant_doctypes") or "").replace("\n", ",")
	items = {item.strip() for item in configured.split(",") if item.strip()}
	return items or DEFAULT_ALLOWED_DESK_DOCTYPES


KNOWN_ERP_FEATURES = {
	"landed cost voucher": {
		"doctype": "Landed Cost Voucher",
		"module": "Stock",
		"route": "/app/landed-cost-voucher",
		"summary": "Allocates additional charges such as freight, customs duty, insurance, and handling to Purchase Receipts or Purchase Invoices so item valuation reflects true landed cost.",
		"steps": [
			"Open Stock, then Landed Cost Voucher, or type Landed Cost Voucher in the global search bar.",
			"Create a new voucher and add the related Purchase Receipt or Purchase Invoice.",
			"Add the extra charges in Taxes and Charges, then use Distribute Charges to allocate them to items.",
			"Save and submit if your role is allowed to submit the voucher.",
		],
	},
	"bom": {"doctype": "BOM", "module": "Manufacturing", "route": "/app/bom", "summary": "Defines finished goods, raw materials, operations, and manufacturing cost structure."},
	"bill of materials": {"doctype": "BOM", "module": "Manufacturing", "route": "/app/bom", "summary": "Defines finished goods, raw materials, operations, and manufacturing cost structure."},
	"trial balance": {"report": "Trial Balance", "module": "Accounts", "route": "/app/query-report/Trial Balance", "summary": "Shows account balances for a company and period."},
	"general ledger": {"report": "General Ledger", "module": "Accounts", "route": "/app/query-report/General Ledger", "summary": "Shows ledger entries by account, party, voucher, and period."},
	"profit and loss": {"report": "Profit and Loss Statement", "module": "Accounts", "route": "/app/query-report/Profit and Loss Statement", "summary": "Shows income, expenses, and profit or loss for a period."},
	"sales by product": {"report": "Item-wise Sales Register", "module": "Accounts", "route": "/app/query-report/Item-wise Sales Register", "summary": "Shows sales invoice item rows and can be filtered/grouped by item."},
	"income statement": {"report": "Profit and Loss Statement", "module": "Accounts", "route": "/app/query-report/Profit and Loss Statement", "summary": "Shows income, expenses, and profit or loss for a period."},
	"product bundle": {
		"doctype": "Product Bundle",
		"module": "Stock",
		"route": "/app/product-bundle",
		"summary": "Groups multiple non-stock or stock items so they can be sold as one package, useful for restaurant combos and meal deals.",
		"steps": [
			"Create the menu items first under Stock or Inventory > Item.",
			"For restaurant menu items that should not be stock-tracked, clear Maintain Stock on the item.",
			"Use the top search bar, type Product Bundle, open it, then click New.",
			"Create a new bundle, choose the parent item, then add child items and quantities.",
		],
	},
	"bundle": {"doctype": "Product Bundle", "module": "Stock", "route": "/app/product-bundle", "summary": "Use Product Bundle for combos, meal deals, and grouped items sold as one product."},
	"bluetooth printer": {
		"module": "Selling",
		"route": "/app/print-format",
		"summary": "58mm receipt printing normally needs the printer paired with the device or OS first, then a compact POS receipt Print Format in VerityPack.",
		"steps": [
			"Pair the Bluetooth printer with the tablet, phone, or computer at operating-system level.",
			"Use a POS Profile and POS Invoice workflow for restaurant billing.",
			"Use or create a 58mm receipt Print Format, then test from a POS Invoice.",
			"If browser printing is used, select the paired printer in the browser print dialog and set paper width to 58mm.",
		],
	},
	"58mm receipt": {"module": "Selling", "route": "/app/print-format", "summary": "Use a compact POS receipt Print Format and browser/device printer settings for 58mm output."},
	"payment reconciliation": {"doctype": "Payment Reconciliation", "module": "Accounts", "route": "/app/payment-reconciliation", "summary": "Helps allocate or reconcile payments and invoices for a party."},
	"unreconciled payments": {"doctype": "Payment Reconciliation", "module": "Accounts", "route": "/app/payment-reconciliation", "summary": "Use Payment Reconciliation and Payment Entry filters to review payments that still need allocation or reconciliation."},
	"user profile": {
		"doctype": "User",
		"module": "Users",
		"route": "/app/user",
		"summary": "RBAC setup normally has four parts: create the User, assign Roles or a Role Profile, configure what each Role can do in Role Permission Manager, then optionally restrict the user to specific records with User Permission.",
		"steps": [
			"Use the top search bar, type User, open Users, click New, enter Email and First Name, make sure Enabled is checked, then Save.",
			"On the saved User, scroll to Roles. Click Add Row and choose the roles the person needs, such as Sales User, Accounts User, Stock User, or System Manager. Save again.",
			"If your organization uses templates of roles, use the search bar to type Role Profile, create a Role Profile, add the roles once, then select that Role Profile on the User instead of adding roles one by one.",
			"Use the search bar to type Role Permission Manager. Pick a Role and a DocType, then set what that role can do: Read means view, Create means add new records, Write means edit, Delete means remove, Submit means finalize documents, Import and Export mean data upload/download, Print and Email control output, and Report controls report access.",
			"Use the search bar to type User Permission only when the user should see only certain linked records, for example one Company, Branch, Warehouse, Territory, Customer, or Supplier.",
			"Test by logging in as that user or using another browser profile, then confirm they can see only what you intended.",
		],
	},
	"create user": {"doctype": "User", "module": "Users", "route": "/app/user", "summary": "Use the search bar to type User, create the user, then assign Roles or a Role Profile."},
	"user permissions": {"doctype": "User Permission", "module": "Users", "route": "/app/user-permission", "summary": "Restricts a user to specific linked records, such as one Company, Warehouse, Territory, Customer, or Branch."},
	"role profile": {"doctype": "Role Profile", "module": "Users", "route": "/app/role-profile", "summary": "A saved group of roles that can be assigned to users instead of manually selecting roles one by one."},
	"role permission manager": {"module": "Users", "route": "/app/role-permission-manager", "summary": "Controls DocType permissions for roles, including read, write, create, delete, submit, import, export, print, email, and report."},
}


def desk_route_for(name, report=False):
	slug = frappe.scrub(name).replace("_", "-")
	return f"/app/query-report/{name}" if report else f"/app/{slug}"


def find_erpnext_feature(query, limit=8):
	try:
		query = (query or "").strip()
		if not query:
			return json.dumps({"success": False, "error": "Query is required."})
		lower = query.lower()
		matches = []
		for key, value in KNOWN_ERP_FEATURES.items():
			if key in lower or lower in key:
				matches.append({"source": "known_erpnext_feature", **value})

		like = f"%{query}%"
		if frappe.db.exists("DocType", "DocType"):
			for row in frappe.get_all("DocType", filters={"name": ["like", like]}, fields=["name", "module", "istable"], limit=limit, ignore_permissions=True):
				if row.get("istable"):
					continue
				name = row.get("name")
				if frappe.has_permission(name, ptype="read") or frappe.has_permission(name, ptype="create"):
					matches.append({"source": "installed_doctype", "doctype": name, "module": row.get("module"), "route": desk_route_for(name)})

		if frappe.db.exists("DocType", "Report"):
			for row in frappe.get_all("Report", filters={"name": ["like", like]}, fields=["name", "module", "report_type"], limit=limit, ignore_permissions=True):
				name = row.get("name")
				try:
					report = frappe.get_doc("Report", name)
					permitted = report.is_permitted() if callable(getattr(report, "is_permitted", None)) else bool(frappe.has_permission("Report", ptype="read", doc=name))
				except Exception:
					permitted = False
				if permitted:
					matches.append({"source": "installed_report", "report": name, "module": row.get("module"), "report_type": row.get("report_type"), "route": desk_route_for(name, report=True)})

		return json.dumps({"success": True, "query": query, "matches": matches[: int(limit or 8)]}, default=str)
	except Exception as e:
		return json.dumps({"success": False, "error": safe_tool_error(e)})


def strip_html(value):
	value = re.sub(r"<[^>]+>", " ", value or "")
	return re.sub(r"\s+", " ", html.unescape(value)).strip()


def build_reference_queries(query):
	base = (query or "").strip()
	queries = []
	if base:
		queries.append(base)
	lower = base.lower()
	replacements = {
		"veritypack": "ERPNext",
		"inventory": "stock",
		"income statement": "profit and loss statement",
		"p&l": "profit and loss statement",
		"pos printer": "POS receipt printer",
		"receipt printer": "POS receipt printer",
	}
	for source, target in replacements.items():
		if source in lower:
			queries.append(re.sub(source, target, base, flags=re.IGNORECASE))
	for suffix in ("ERPNext docs", "ERPNext manual"):
		if base and suffix.lower() not in lower:
			queries.append(f"{base} {suffix}")
	seen = set()
	unique = []
	for item in queries:
		key = item.lower().strip()
		if key and key not in seen:
			seen.add(key)
			unique.append(item.strip())
	return unique[:4]


ERPNext_DOCS_ROOT = "https://docs.frappe.io/erpnext"
ERPNext_DOCS_ALLOWED_PREFIX = "https://docs.frappe.io/erpnext/"
ERPNext_DOCS_INDEX_LIMIT = 1500


def absolute_docs_url(href):
	if not href:
		return ""
	if href.startswith("https://docs.frappe.io/erpnext"):
		return href.split("#", 1)[0]
	if href.startswith("/erpnext"):
		return f"https://docs.frappe.io{href}".split("#", 1)[0]
	return ""


def docs_title_from_url(url):
	last = (url or "").rstrip("/").rsplit("/", 1)[-1]
	return re.sub(r"[-_]+", " ", last).strip().title() or "Official Reference"


def extract_docs_article(page_text, title=""):
	text = re.sub(r"<script[^>]*>.*?</script>", " ", page_text or "", flags=re.I | re.S)
	text = re.sub(r"<style[^>]*>.*?</style>", " ", text, flags=re.I | re.S)
	content = strip_html(text)
	title = (title or "").strip()
	markers = []
	if title:
		markers.extend([f"# {title}", title])
	markers.extend(["Copy page as Markdown for LLMs", "Was this article helpful?"])
	start_positions = []
	for marker in markers:
		idx = content.find(marker)
		if idx >= 0:
			start_positions.append(idx)
	if start_positions:
		content = content[min(start_positions):]
	if title and content.startswith(title):
		content = f"# {content}"
	stop_markers = ["Was this article helpful?", "Give Feedback", "Last updated", "Edit this page", "Contents"]
	stop_positions = [content.find(marker) for marker in stop_markers if content.find(marker) > 0]
	if stop_positions:
		content = content[: min(stop_positions)]
	content = re.sub(r"Copy page as Markdown for LLMs", "", content)
	content = re.sub(r"(?m)^\s{0,3}#{1,6}\s*", "", content)
	content = re.sub(r"\bESC Type to search documentation.*?On this page\b", "", content, flags=re.I)
	content = re.sub(r"\s+", " ", content).strip()
	return content[:6000]

def extract_erpnext_doc_links(page_text):
	links = []
	for href, label in re.findall(r'<a[^>]+href=["\']([^"\']+)["\'][^>]*>(.*?)</a>', page_text or "", flags=re.I | re.S):
		url = absolute_docs_url(html.unescape(href))
		if not url or not url.startswith(ERPNext_DOCS_ALLOWED_PREFIX):
			continue
		if any(part in url for part in ("/cloud/", "/framework/", "/frappe-hr/")):
			continue
		title = strip_html(label) or docs_title_from_url(url)
		if not title or title.lower() in {"erpnext", "framework", "cloud", "github", "edit this page"}:
			title = docs_title_from_url(url)
		links.append({"title": title, "url": url})
	return links


def get_erpnext_docs_index(session, headers):
	cache_key = "verity_ai:erpnext_docs_index:v3"
	cached = frappe.cache().get_value(cache_key)
	if cached:
		return cached
	try:
		queue = [ERPNext_DOCS_ROOT]
		queued = set(queue)
		visited = set()
		links = []
		while queue and len(visited) < ERPNext_DOCS_INDEX_LIMIT:
			url = queue.pop(0)
			if url in visited:
				continue
			visited.add(url)
			try:
				response = session.get(url, headers=headers, timeout=15)
			except Exception:
				continue
			if response.status_code != 200:
				continue
			page_links = extract_erpnext_doc_links(response.text)
			links.extend(page_links)
			for item in page_links:
				link = item.get("url")
				if link and link not in queued and len(queued) < ERPNext_DOCS_INDEX_LIMIT:
					queued.add(link)
					queue.append(link)
		seen = set()
		unique = []
		for item in links:
			key = item.get("url")
			if key and key not in seen:
				seen.add(key)
				unique.append(item)
		frappe.cache().set_value(cache_key, unique, expires_in_sec=86400)
		return unique
	except Exception:
		return []


def refresh_erpnext_docs_index():
	try:
		headers = {"User-Agent": "VerityAI/1.0 VerityPack Assistant"}
		session = requests.Session()
		cache = frappe.cache()
		if hasattr(cache, "delete_value"):
			cache.delete_value("verity_ai:erpnext_docs_index:v3")
		index = get_erpnext_docs_index(session, headers)
		return json.dumps({"success": True, "indexed_pages": len(index), "primary_source": "official_erpnext_docs"})
	except Exception as e:
		return json.dumps({"success": False, "error": safe_tool_error(e)})


def fetch_docs_page(session, url, headers, title=""):
	if not url or not url.startswith(ERPNext_DOCS_ALLOWED_PREFIX):
		return ""
	cache_key = f"verity_ai:erpnext_doc:v2:{url}"
	cached = frappe.cache().get_value(cache_key)
	if cached:
		return cached
	try:
		response = session.get(url, headers=headers, timeout=15)
		if response.status_code != 200:
			return ""
		content = extract_docs_article(response.text, title or docs_title_from_url(url))
		frappe.cache().set_value(cache_key, content, expires_in_sec=86400)
		return content
	except Exception:
		return ""

REFERENCE_STOPWORDS = {
	"about", "after", "before", "create", "does", "docs", "documentation", "erpnext", "from", "have", "help", "how", "into", "items", "make", "manual", "need", "official", "setup", "that", "the", "this", "what", "when", "where", "with", "your"
}


def reference_tokens(value):
	return [token for token in re.findall(r"[a-z0-9]{3,}", (value or "").lower()) if token not in REFERENCE_STOPWORDS]


def score_reference_result(query, title, excerpt, search_query="", rank=0):
	query_text = f"{query or ''} {search_query or ''}".lower()
	title_text = (title or "").lower()
	excerpt_text = (excerpt or "").lower()
	combined = f"{title_text}\n{excerpt_text}"
	tokens = reference_tokens(query_text)
	if not tokens:
		return 0
	score = 0
	for token in tokens:
		if token in title_text:
			score += 10
		if token in excerpt_text:
			score += min(excerpt_text.count(token), 4) * 2
	phrases = [phrase.strip() for phrase in re.split(r"\s+(?:for|in|with|and|or|to)\s+", (query or "").lower()) if len(phrase.strip()) >= 5]
	for phrase in phrases:
		if phrase in title_text:
			score += 18
		elif phrase in combined:
			score += 8
	for bigram in zip(tokens, tokens[1:]):
		phrase = " ".join(bigram)
		if phrase in title_text:
			score += 10
		elif phrase in combined:
			score += 4
	return score - (rank * 0.25)

def fetch_discourse_topic(session, topic_id, headers):
	if not topic_id:
		return ""
	cache_key = f"verity_ai:forum_topic:{topic_id}"
	cached = frappe.cache().get_value(cache_key)
	if cached:
		return cached
	try:
		response = session.get(f"https://discuss.frappe.io/t/{topic_id}.json", headers=headers, timeout=12)
		if response.status_code != 200:
			return ""
		posts = response.json().get("post_stream", {}).get("posts", [])
		parts = []
		for post in posts[:6]:
			text = strip_html(post.get("cooked") or post.get("excerpt") or "")
			if text:
				parts.append(text[:1200])
		content = "\n".join(parts)[:5000]
		frappe.cache().set_value(cache_key, content, expires_in_sec=86400)
		return content
	except Exception:
		return ""


def search_frappe_resources(query, limit=5):
	try:
		query = (query or "").strip()
		if not query:
			return json.dumps({"success": False, "error": "Query is required."})
		limit = min(int(limit or 5), 8)
		candidates = []
		seen_topics = set()
		headers = {"User-Agent": "VerityAI/1.0 VerityPack Assistant"}
		session = requests.Session()

		doc_shortlist = []
		for rank, page in enumerate(get_erpnext_docs_index(session, headers)):
			title = page.get("title") or "Official Reference"
			url = page.get("url")
			index_text = f"{title} {url}"
			index_score = score_reference_result(query, title, index_text, "", rank)
			if index_score <= 0:
				continue
			doc_shortlist.append({"title": title, "url": url, "_index_score": index_score})

		doc_shortlist.sort(key=lambda item: item.get("_index_score", 0), reverse=True)
		for page in doc_shortlist[: max(limit * 4, 12)]:
			title = page.get("title") or "Official Reference"
			url = page.get("url")
			content = fetch_docs_page(session, url, headers, title)
			guidance = content or f"{title} {url}"
			content_score = score_reference_result(query, title, guidance, "", 0)
			score = (page.get("_index_score", 0) * 3) + min(content_score, 40)
			if score <= 0:
				continue
			candidates.append(
				{
					"source": "Official Reference",
					"title": title,
					"excerpt": guidance[:2400],
					"confidence": "official_docs",
					"_score": score,
				}
			)

		candidates.sort(key=lambda item: item.get("_score", 0), reverse=True)
		results = []
		for item in candidates[:limit]:
			item.pop("_score", None)
			results.append(item)

		if len(results) < limit:
			max_topics = max((limit - len(results)) * 5, 15)
			forum_candidates = []
			for search_query in build_reference_queries(query):
				try:
					forum = session.get("https://discuss.frappe.io/search.json", params={"q": search_query}, headers=headers, timeout=12)
				except Exception:
					continue
				if forum.status_code != 200:
					continue
				for rank, topic in enumerate(forum.json().get("topics", [])[:max_topics]):
					topic_id = topic.get("id")
					if topic_id in seen_topics:
						continue
					seen_topics.add(topic_id)
					title = strip_html(topic.get("title") or "Reference result")
					content = fetch_discourse_topic(session, topic_id, headers)
					excerpt = strip_html(topic.get("blurb") or topic.get("excerpt") or "")
					guidance = content or excerpt
					if not guidance:
						continue
					score = score_reference_result(query, title, guidance, search_query, rank)
					if score <= 0:
						continue
					forum_candidates.append(
						{
							"source": "Reference Knowledge",
							"title": title,
							"excerpt": guidance[:1800],
							"confidence": "forum_topic" if content else "search_excerpt",
							"_score": score,
						}
					)
			forum_candidates.sort(key=lambda item: item.get("_score", 0), reverse=True)
			for item in forum_candidates[: limit - len(results)]:
				item.pop("_score", None)
				results.append(item)

		return json.dumps({"success": True, "query": query, "primary_source": "official_erpnext_docs", "results": results[:limit], "result_count": len(results[:limit])}, default=str)
	except Exception as e:
		return json.dumps({"success": False, "error": safe_tool_error(e)})


def column_label(column):
	if isinstance(column, dict):
		return column.get("label") or column.get("fieldname") or column.get("field") or "Value"
	if isinstance(column, (list, tuple)) and column:
		return str(column[0])
	return str(column or "Value").split(":", 1)[0]


def column_field(column):
	if isinstance(column, dict):
		return column.get("fieldname") or column.get("field") or column.get("label")
	if isinstance(column, (list, tuple)) and column:
		return str(column[0])
	return str(column or "").split(":", 1)[0]


def normalize_table(columns, rows):
	rows = list(rows or [])
	if not columns and rows:
		first = rows[0]
		if isinstance(first, dict):
			columns = list(first.keys())
		else:
			columns = [f"Column {idx + 1}" for idx in range(len(first or []))]
	headers = [column_label(column) for column in (columns or [])]
	fields = [column_field(column) for column in (columns or [])]
	table = []
	for row in rows:
		if isinstance(row, dict):
			table.append([row.get(field) for field in fields])
		elif isinstance(row, (list, tuple)):
			table.append(list(row))
		else:
			table.append([row])
	return headers, table


def safe_filename(title):
	name = re.sub(r"[^A-Za-z0-9_-]+", "_", title or "veritypack_export").strip("_")
	return name[:80] or "veritypack_export"


def save_private_file(filename, content):
	from frappe.utils.file_manager import save_file

	file_doc = save_file(filename, content, None, None, is_private=1)
	return {"file_name": file_doc.file_name, "file_url": file_doc.file_url}


def make_csv_export(title, headers, table):
	buffer = io.StringIO()
	writer = csv.writer(buffer)
	writer.writerow(headers)
	writer.writerows(table)
	return save_private_file(f"{safe_filename(title)}.csv", buffer.getvalue())


def make_xlsx_export(title, headers, table):
	try:
		from frappe.utils.xlsxutils import make_xlsx

		xlsx = make_xlsx([headers, *table], safe_filename(title)[:31])
		content = xlsx.getvalue() if hasattr(xlsx, "getvalue") else xlsx
		return save_private_file(f"{safe_filename(title)}.xlsx", content)
	except Exception:
		csv_file = make_csv_export(title, headers, table)
		csv_file["format"] = "csv"
		csv_file["note"] = "Excel export fell back to CSV."
		return csv_file


def make_pdf_export(title, headers, table):
	from frappe.utils.pdf import get_pdf

	head = "".join(f"<th>{html.escape(str(label or ''))}</th>" for label in headers)
	body = "".join(
		"<tr>" + "".join(f"<td>{html.escape(str(value if value is not None else ''))}</td>" for value in row) + "</tr>"
		for row in table[:500]
	)
	content = f"""
	<h2>{html.escape(str(title or 'VerityPack Export'))}</h2>
	<table border="1" cellspacing="0" cellpadding="4">
		<thead><tr>{head}</tr></thead>
		<tbody>{body}</tbody>
	</table>
	"""
	return save_private_file(f"{safe_filename(title)}.pdf", get_pdf(content))


def make_table_exports(title, columns, rows):
	try:
		headers, table = normalize_table(columns, rows)
		if not headers or not table:
			return []
		exports = [{"format": "xlsx", **make_xlsx_export(title, headers, table)}]
		try:
			exports.append({"format": "pdf", **make_pdf_export(title, headers, table)})
		except Exception as e:
			exports.append({"format": "pdf", "error": safe_tool_error(e)})
		return exports
	except Exception as e:
		return [{"error": safe_tool_error(e)}]

def user_has_any_role(roles):
	user_roles = set(frappe.get_roles(frappe.session.user))
	return bool(user_roles.intersection(set(roles)))


def sensitive_action_requires_approval(config, action):
	return (action or "").lower().strip() in SENSITIVE_DOCUMENT_ACTIONS and bool(config.get("require_approval_for_sensitive_actions"))


def approval_result(success, message=None, **extra):
	payload = {"success": success}
	if message:
		payload["message" if success else "error"] = message
	payload.update(extra)
	return json.dumps(payload, default=str)


def stage_ai_action_approval(config, tenant_name, session_name, user_identifier, platform, action, doctype, name=None, values=None, filters=None, fields=None, limit=20, risk_level="High", reason=None):
	try:
		action = (action or "").lower().strip()
		if action not in {"create", "update", "delete", "submit", "cancel"}:
			return approval_result(False, "Only create, update, delete, submit, or cancel actions can be staged for approval.")
		blocked = validate_ai_document_action(config, action, doctype, confirmed=True)
		if blocked:
			return approval_result(False, blocked)
		error = require_allowed_doctype(config, doctype)
		if error and action != "create":
			return approval_result(False, error)
		if action == "create" and not frappe.has_permission(doctype, ptype="create"):
			return approval_result(False, f"You do not have permission to create {doctype}.")
		approval = frappe.get_doc(
			{
				"doctype": "AI Action Approval",
				"tenant": tenant_name or config.get("tenant"),
				"chat_session": session_name,
				"platform": platform,
				"requested_by": user_identifier or frappe.session.user,
				"status": "Pending",
				"risk_level": risk_level or "High",
				"action": action,
				"target_doctype": doctype,
				"target_name": name,
				"values_json": json.dumps(values or {}, default=str),
				"filters_json": json.dumps(filters or {}, default=str),
				"fields_json": json.dumps(fields or [], default=str),
				"approval_notes": reason,
			}
		)
		approval.insert(ignore_permissions=True)
		frappe.db.commit()
		return approval_result(True, f"Approval request {approval.name} has been created for {action} on {doctype}.", approval=approval.name, status="Pending")
	except Exception as e:
		frappe.db.rollback()
		return approval_result(False, safe_tool_error(e))


def execute_ai_action_approval(doc, method=None):
	if getattr(doc.flags, "executing_ai_action", False) or doc.status != "Approved":
		return
	if not user_has_any_role(AI_ACTION_APPROVER_ROLES):
		doc.db_set("status", "Failed", update_modified=False)
		doc.db_set("execution_result", json.dumps({"success": False, "error": "Only an AI administrator, sales manager, or system manager can approve AI actions."}), update_modified=False)
		return
	doc.flags.executing_ai_action = True
	try:
		config = frappe.get_doc("AI Configuration", {"tenant": doc.tenant}) if doc.tenant else None
		if not config:
			frappe.throw("AI Configuration was not found for this tenant.")
		result = crud_erpnext_document(
			config,
			action=doc.action,
			doctype=doc.target_doctype,
			name=doc.target_name,
			values=json.loads(doc.values_json or "{}"),
			filters=json.loads(doc.filters_json or "{}"),
			fields=json.loads(doc.fields_json or "[]"),
			confirmed=True,
			approval_authorized=True,
		)
		data = json.loads(result or "{}")
		doc.db_set("execution_result", json.dumps(data, default=str), update_modified=False)
		doc.db_set("approved_by", frappe.session.user, update_modified=False)
		doc.db_set("status", "Executed" if data.get("success") else "Failed", update_modified=False)
	except Exception as e:
		frappe.db.rollback()
		doc.db_set("execution_result", json.dumps({"success": False, "error": safe_tool_error(e)}, default=str), update_modified=False)
		doc.db_set("status", "Failed", update_modified=False)

def configured_blocked_action_doctypes(config):
	configured = (config.get("blocked_ai_action_doctypes") or "").replace("\n", ",") if config else ""
	items = {item.strip() for item in configured.split(",") if item.strip()}
	return configured_blocked_doctypes(config)


def validate_ai_document_action(config, action, doctype, confirmed=False):
	action = (action or "").lower().strip()
	if action_risk(action, doctype) == "Blocked" or (action in {"create", "update", "delete", "submit", "cancel"} and doctype in configured_blocked_action_doctypes(config)):
		return f"AI write actions are blocked for sensitive DocType {doctype}. Use the normal VerityPack UI with administrator oversight."
	if action in SENSITIVE_DOCUMENT_ACTIONS and config.get("require_confirmation_for_sensitive_actions") and not confirmed:
		return f"Please confirm that you want me to {action} {doctype}. This action changes finalized business records."
	return None

def require_allowed_doctype(config, doctype):
	allowed = allowed_desk_doctypes(config)
	if "*" not in allowed and doctype not in allowed and not config.get("enable_erpnext_assistant"):
		return "DocType is not enabled for the assistant."
	if not frappe.has_permission(doctype, ptype="read"):
		return f"You do not have permission to access {doctype}."
	return None

def apply_document_defaults(doctype, values):
	values = dict(values or {})
	if doctype == "Customer":
		from verity_ai.sales.quotation_flow import default_customer_group

		values.setdefault("customer_name", values.get("name") or values.get("customer") or values.get("customer_name"))
		values.setdefault("customer_type", "Company")
		if not values.get("customer_group"):
			values["customer_group"] = default_customer_group()
		if not values.get("territory") and frappe.db.exists("Territory", "All Territories"):
			values["territory"] = "All Territories"
	if doctype == "Supplier":
		values.setdefault("supplier_name", values.get("name") or values.get("supplier") or values.get("supplier_name"))
		values.setdefault("supplier_type", "Company")
	if doctype == "Lead":
		values.setdefault("lead_name", values.get("name") or values.get("lead_name"))
	return {key: value for key, value in values.items() if not key.startswith("_") and key not in {"doctype", "docstatus", "idx"}}


def get_erpnext_records(config, doctype, filters=None, fields=None, limit=10):
	try:
		error = require_allowed_doctype(config, doctype)
		if error:
			return json.dumps({"success": False, "error": error})
		limit = min(int(limit or 10), 50)
		fields = safe_read_fields(doctype, fields)
		rows = frappe.get_list(doctype, filters=filters or {}, fields=fields, limit_page_length=limit)
		exports = make_table_exports(doctype, fields, rows)
		return json.dumps({"success": True, "doctype": doctype, "rows": rows, "exports": exports}, default=str)
	except Exception as e:
		return json.dumps({"success": False, "error": safe_tool_error(e)})


def create_erpnext_document(config, doctype, values):
	try:
		blocked = validate_ai_document_action(config, "create", doctype)
		if blocked:
			return json.dumps({"success": False, "error": blocked})
		if not config.get("enable_erpnext_write_actions"):
			return json.dumps({"success": False, "error": "Create and update actions are disabled for the assistant."})
		if doctype not in allowed_desk_doctypes(config):
			return json.dumps({"success": False, "error": "DocType is not enabled for the assistant."})
		if not frappe.has_permission(doctype, ptype="create"):
			return json.dumps({"success": False, "error": f"You do not have permission to create {doctype}."})
		data = apply_document_defaults(doctype, sanitized_document_values(doctype, values))
		doc = frappe.get_doc({"doctype": doctype, **data})
		doc.insert()
		frappe.db.commit()
		return json.dumps({"success": True, "doctype": doctype, "name": doc.name, "message": f"{doctype} {doc.name} created."}, default=str)
	except Exception as e:
		frappe.db.rollback()
		return json.dumps({"success": False, "error": safe_tool_error(e)})


def update_erpnext_document(config, doctype, name, values):
	try:
		blocked = validate_ai_document_action(config, "update", doctype)
		if blocked:
			return json.dumps({"success": False, "error": blocked})
		if not config.get("enable_erpnext_write_actions"):
			return json.dumps({"success": False, "error": "Create and update actions are disabled for the assistant."})
		error = require_allowed_doctype(config, doctype)
		if error:
			return json.dumps({"success": False, "error": error})
		doc = frappe.get_doc(doctype, name)
		doc.check_permission("write")
		for field, value in sanitized_document_values(doctype, values).items():
			doc.set(field, value)
		doc.save()
		frappe.db.commit()
		return json.dumps({"success": True, "doctype": doctype, "name": doc.name, "message": f"{doctype} {doc.name} updated."}, default=str)
	except Exception as e:
		frappe.db.rollback()
		return json.dumps({"success": False, "error": safe_tool_error(e)})


SENSITIVE_FIELD_PATTERN = re.compile(r"(?i)(password|passwd|pwd|secret|token|api[_-]?key|authorization|auth[_-]?token|access[_-]?key|access[_-]?token|private[_-]?key)")

def field_allowed_for_write(field):
	return not (field.fieldname.startswith("_") or field.fieldname in {"name", "owner", "creation", "modified", "modified_by", "docstatus", "idx"} or field.read_only or field.fieldtype in {"Section Break", "Column Break", "HTML", "Button", "Fold", "Password"} or SENSITIVE_FIELD_PATTERN.search(field.fieldname or ""))


def get_doctype_schema(doctype):
	try:
		if not frappe.db.exists("DocType", doctype):
			return json.dumps({"success": False, "error": f"DocType {doctype} was not found."})
		if not frappe.has_permission(doctype, ptype="read") and not frappe.has_permission(doctype, ptype="create"):
			return json.dumps({"success": False, "error": f"You do not have permission to access {doctype}."})
		meta = frappe.get_meta(doctype)
		fields = []
		for field in meta.fields:
			if field.hidden:
				continue
			fields.append({"fieldname": field.fieldname, "label": field.label, "fieldtype": field.fieldtype, "options": field.options, "reqd": bool(field.reqd), "read_only": bool(field.read_only), "default": field.default, "in_list_view": bool(field.in_list_view)})
		return json.dumps({"success": True, "doctype": doctype, "title_field": meta.title_field, "is_submittable": bool(meta.is_submittable), "fields": fields}, default=str)
	except Exception as e:
		return json.dumps({"success": False, "error": safe_tool_error(e)})


def sanitized_document_values(doctype, values):
	meta = frappe.get_meta(doctype)
	allowed = {field.fieldname for field in meta.fields if field_allowed_for_write(field)}
	return {key: value for key, value in (values or {}).items() if key in allowed}


def field_safe_for_ai(fieldname, field=None):
	if not fieldname or str(fieldname).startswith("_"):
		return False
	if field and getattr(field, "fieldtype", None) == "Password":
		return False
	return not SENSITIVE_FIELD_PATTERN.search(str(fieldname))


def safe_read_fields(doctype, fields=None):
	meta = frappe.get_meta(doctype)
	field_map = {field.fieldname: field for field in meta.fields}
	requested = fields or ["name", "modified"]
	safe = []
	for fieldname in requested:
		fieldname = str(fieldname or "").strip()
		if fieldname == "*":
			continue
		if fieldname in {"name", "owner", "creation", "modified", "modified_by", "docstatus"}:
			safe.append(fieldname)
		elif field_safe_for_ai(fieldname, field_map.get(fieldname)):
			safe.append(fieldname)
	return safe or ["name", "modified"]


def sanitize_document_for_ai(doc):
	meta = frappe.get_meta(doc.doctype)
	field_map = {field.fieldname: field for field in meta.fields}
	data = doc.as_dict()
	for key in list(data.keys()):
		if key in {"doctype", "name", "owner", "creation", "modified", "modified_by", "docstatus", "idx"}:
			continue
		if not field_safe_for_ai(key, field_map.get(key)):
			data[key] = "[redacted]"
	return data

def crud_erpnext_document(config, action, doctype, name=None, values=None, filters=None, fields=None, limit=20, confirmed=False, approval_authorized=False):
	try:
		action = (action or "").lower().strip()
		blocked = validate_ai_document_action(config, action, doctype, confirmed=confirmed)
		if blocked:
			return json.dumps({"success": False, "error": blocked})
		if sensitive_action_requires_approval(config, action) and not approval_authorized:
			return json.dumps({"success": False, "approval_required": True, "error": f"{action.title()} for {doctype} requires manager approval. Stage an AI Action Approval request."})
		error = require_allowed_doctype(config, doctype)
		if error and action not in {"create", "schema"}:
			return json.dumps({"success": False, "error": error})
		if action == "schema":
			return get_doctype_schema(doctype)
		if action == "list":
			limit = min(int(limit or 20), 100)
			rows = frappe.get_list(doctype, filters=filters or {}, fields=safe_read_fields(doctype, fields), limit_page_length=limit)
			return json.dumps({"success": True, "doctype": doctype, "rows": rows, "row_count": len(rows)}, default=str)
		if action == "read":
			if not name:
				return json.dumps({"success": False, "error": "Document name is required."})
			doc = frappe.get_doc(doctype, name)
			doc.check_permission("read")
			return json.dumps({"success": True, "doctype": doctype, "name": doc.name, "doc": sanitize_document_for_ai(doc)}, default=str)
		if action == "create":
			if not config.get("enable_erpnext_write_actions"):
				return json.dumps({"success": False, "error": "Create and update actions are disabled for the assistant."})
			if not frappe.has_permission(doctype, ptype="create"):
				return json.dumps({"success": False, "error": f"You do not have permission to create {doctype}."})
			data = apply_document_defaults(doctype, sanitized_document_values(doctype, values))
			doc = frappe.get_doc({"doctype": doctype, **data})
			doc.insert()
			frappe.db.commit()
			return json.dumps({"success": True, "action": action, "doctype": doctype, "name": doc.name, "message": f"{doctype} {doc.name} created."}, default=str)
		if not name:
			return json.dumps({"success": False, "error": "Document name is required."})
		doc = frappe.get_doc(doctype, name)
		if action == "update":
			if not config.get("enable_erpnext_write_actions"):
				return json.dumps({"success": False, "error": "Create and update actions are disabled for the assistant."})
			doc.check_permission("write")
			for field, value in sanitized_document_values(doctype, values).items():
				doc.set(field, value)
			doc.save()
		elif action == "delete":
			doc.check_permission("delete")
			doc.delete()
		elif action == "submit":
			doc.check_permission("submit")
			doc.submit()
		elif action == "cancel":
			doc.check_permission("cancel")
			doc.cancel()
		else:
			return json.dumps({"success": False, "error": "Action must be schema, list, read, create, update, delete, submit, or cancel."})
		frappe.db.commit()
		return json.dumps({"success": True, "action": action, "doctype": doctype, "name": name}, default=str)
	except Exception as e:
		frappe.db.rollback()
		return json.dumps({"success": False, "error": safe_tool_error(e)})

def default_company():
	company = frappe.defaults.get_user_default("Company") or frappe.db.get_single_value("Global Defaults", "default_company")
	if company:
		return company
	companies = frappe.get_all("Company", fields=["name"], limit=1)
	return companies[0].get("name") if companies else None


REPORT_ALIASES = {
	"income statement": "Profit and Loss Statement",
	"statement of profit and loss": "Profit and Loss Statement",
	"p&l": "Profit and Loss Statement",
	"p and l": "Profit and Loss Statement",
	"expenses": "Profit and Loss Statement",
	"expense report": "Profit and Loss Statement",
	"sales report": "Item-wise Sales Register",
	"sales per item": "Item-wise Sales Register",
	"sales by item": "Item-wise Sales Register",
	"sales by product": "Item-wise Sales Register",
}


def resolve_report_name(report_name):
	name = (report_name or "").strip()
	alias = REPORT_ALIASES.get(name.lower())
	if alias:
		return alias
	if frappe.db.exists("Report", name):
		return name
	matches = frappe.get_all("Report", filters={"name": ["like", f"%{name}%"]}, fields=["name"], limit=1, ignore_permissions=True)
	return matches[0].get("name") if matches else name

def normalize_date(value):
	if not value:
		return None
	try:
		return frappe.utils.getdate(value).isoformat()
	except Exception:
		return None


def normalize_report_filters(report_name, filters=None, from_date=None, to_date=None):
	filters = dict(filters or {})
	normalized = {}
	for key, value in filters.items():
		field = frappe.scrub(str(key)).replace("_date_", "_date")
		field = {
			"from": "from_date",
			"fromdate": "from_date",
			"start_date": "from_date",
			"period_start_date": "from_date",
			"start": "from_date",
			"to": "to_date",
			"todate": "to_date",
			"end_date": "to_date",
			"period_end_date": "to_date",
			"end": "to_date",
		}.get(field, field)
		normalized[field] = value

	if from_date:
		normalized["from_date"] = from_date
	if to_date:
		normalized["to_date"] = to_date

	date_reports = {
		"trial balance",
		"profit and loss statement",
		"general ledger",
		"accounts payable",
		"accounts receivable",
		"item-wise sales register",
		"sales analytics",
	}
	if (report_name or "").lower() in date_reports:
		today = frappe.utils.getdate()
		normalized["from_date"] = normalize_date(normalized.get("from_date")) or today.replace(month=1, day=1).isoformat()
		normalized["to_date"] = normalize_date(normalized.get("to_date")) or today.isoformat()


	financial_reports = {"profit and loss statement", "trial balance", "balance sheet", "cash flow"}
	if (report_name or "").lower() in financial_reports:
		if normalized.get("from_date") and "period_start_date" not in normalized:
			normalized["period_start_date"] = normalized.get("from_date")
		if normalized.get("to_date") and "period_end_date" not in normalized:
			normalized["period_end_date"] = normalized.get("to_date")
	for field in ("from_date", "to_date", "posting_date", "transaction_date"):
		if field in normalized:
			normalized[field] = normalize_date(normalized.get(field)) or normalized.get(field)

	company = default_company()
	if company and "company" not in normalized:
		normalized["company"] = company
	return normalized


def run_erpnext_report(config, report_name, filters=None, from_date=None, to_date=None):
	report_name = resolve_report_name(report_name)
	old_mute = getattr(frappe.flags, "mute_messages", False)
	try:
		if not frappe.db.exists("Report", report_name):
			return json.dumps({"success": False, "error": f"Report {report_name} was not found."})
		report = frappe.get_doc("Report", report_name)
		if callable(getattr(report, "is_permitted", None)):
			if not report.is_permitted():
				return json.dumps({"success": False, "error": f"You do not have permission to run {report_name}."})
		else:
			report.check_permission("read")
		filters = normalize_report_filters(report_name, filters, from_date, to_date)
		from frappe.desk.query_report import run

		frappe.flags.mute_messages = True
		try:
			result = run(report_name, filters=filters, ignore_prepared_report=True)
		except TypeError:
			result = run(report_name, filters=filters)
		finally:
			frappe.local.message_log = []

		if isinstance(result, (list, tuple)):
			columns = result[0] if len(result) > 0 else []
			rows = result[1] if len(result) > 1 else []
		else:
			columns = result.get("columns") or []
			rows = result.get("result") or result.get("data") or []
		return json.dumps(
			{"success": True, "report": report_name, "filters": filters, "columns": columns, "rows": rows[:100], "row_count": len(rows), "exports": make_table_exports(report_name, columns, rows)},
			default=str,
		)
	except Exception as e:
		frappe.local.message_log = []
		return json.dumps({"success": False, "error": safe_tool_error(e), "filters": normalize_report_filters(report_name, filters, from_date, to_date)})
	finally:
		frappe.flags.mute_messages = old_mute

def get_unreconciled_payments(config, limit=50):
	try:
		error = require_allowed_doctype(config, "Payment Entry")
		if error:
			return json.dumps({"success": False, "error": error})
		limit = min(int(limit or 50), 100)
		fields = ["name", "posting_date", "party_type", "party", "paid_amount", "received_amount", "unallocated_amount", "mode_of_payment", "reference_no"]
		rows = frappe.get_list(
			"Payment Entry",
			filters=[["Payment Entry", "docstatus", "=", 1], ["Payment Entry", "unallocated_amount", ">", 0]],
			fields=fields,
			order_by="posting_date desc",
			limit_page_length=limit,
		)
		exports = make_table_exports("Unreconciled Payments", fields, rows)
		return json.dumps({"success": True, "rows": rows, "row_count": len(rows), "exports": exports}, default=str)
	except Exception as e:
		return json.dumps({"success": False, "error": safe_tool_error(e)})

def run_safe_site_query(config, sql):
	try:
		if not config.get("enable_safe_query_tool"):
			return json.dumps({"success": False, "error": "Safe query tool is disabled."})
		if not user_has_any_role({"System Manager", "Report Manager", "Accounts Manager"}):
			return json.dumps({"success": False, "error": "Only report or system managers can run raw read-only queries."})
		statement = (sql or "").strip()
		lower = statement.lower()
		blocked = [";", "insert", "update", "delete", "drop", "alter", "truncate", "create", "replace", "grant", "revoke", "outfile", "load_file"]
		if not lower.startswith("select") or any(term in lower for term in blocked):
			return json.dumps({"success": False, "error": "Only one safe read-only SELECT query is allowed."})
		if " limit " not in lower:
			statement = f"{statement} limit 100"
		rows = frappe.db.sql(statement, as_dict=True)
		exports = make_table_exports("Safe Query Result", list(rows[0].keys()) if rows else [], rows)
		return json.dumps({"success": True, "rows": rows, "exports": exports}, default=str)
	except Exception as e:
		return json.dumps({"success": False, "error": safe_tool_error(e)})
