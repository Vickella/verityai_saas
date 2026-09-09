import hashlib
import io
import json
import re
import zipfile

import frappe
from frappe.utils import cint, now_datetime

from verityai_saas.websites.definitions import validate_definition


MAX_ARCHIVE_BYTES = 5 * 1024 * 1024
MAX_EXPANDED_BYTES = 10 * 1024 * 1024
MAX_ARCHIVE_FILES = 20
MANIFEST_NAMES = {"template.json", "website-template.json"}
KEY_PATTERN = re.compile(r"^[a-z0-9]+(?:[._-][a-z0-9]+)*$")
PLACEHOLDERS = {"business_name", "business_nature"}


BUILT_IN_TEMPLATES = (
	{
		"key": "starter-v1", "name": "Business Starter", "category": "Business",
		"description": "A clear, conversion-focused home page for a growing organisation.",
		"definition": {
			"schema_version": 1,
			"site": {"title": "{{business_name}}", "description": "A trusted {{business_nature}} organisation.", "language": "en"},
			"brand": {"primary_color": "#2457d6", "secondary_color": "#0f766e", "background_color": "#ffffff", "text_color": "#172033"},
			"navigation": [{"label": "Home", "page_slug": "home"}],
			"pages": [{"slug": "home", "title": "Home", "description": "Welcome to {{business_name}}", "sections": [
				{"id": "hero-1", "type": "hero", "eyebrow": "{{business_nature}}", "heading": "Welcome to {{business_name}}", "body": "Discover practical support designed around your needs.", "primary_action": {"label": "Contact us", "url": "/contact"}},
				{"id": "features-1", "type": "features", "heading": "How we can help", "items": [{"title": "Trusted support", "body": "Clear, dependable service from a team that cares."}, {"title": "Built around you", "body": "Solutions shaped around your real goals."}, {"title": "Easy to begin", "body": "Contact us and take the next step with confidence."}]},
				{"id": "cta-1", "type": "cta", "heading": "Ready to get started?", "body": "Talk to {{business_name}} today.", "primary_action": {"label": "Get in touch", "url": "/contact"}},
			]}],
			"integrations": {"widget_enabled": True, "whatsapp_enabled": False, "crm_enabled": True},
		},
	},
	{
		"key": "community-v1", "name": "Community & Faith", "category": "Community",
		"description": "A warm, welcoming layout for churches, charities and community groups.",
		"definition": {
			"schema_version": 1,
			"site": {"title": "{{business_name}}", "description": "Welcome to our {{business_nature}} community.", "language": "en"},
			"brand": {"primary_color": "#6d4aff", "secondary_color": "#c47f17", "background_color": "#fffdf8", "text_color": "#211b35"},
			"navigation": [{"label": "Home", "page_slug": "home"}],
			"pages": [{"slug": "home", "title": "Home", "description": "A place to belong", "sections": [
				{"id": "hero-1", "type": "hero", "eyebrow": "You are welcome here", "heading": "Find hope and community at {{business_name}}", "body": "Connect, grow and take your next step with a community that is ready to welcome you.", "primary_action": {"label": "Plan your visit", "url": "/contact"}},
				{"id": "features-1", "type": "features", "heading": "There is a place for you", "items": [{"title": "Connect", "body": "Meet people and build meaningful relationships."}, {"title": "Grow", "body": "Find encouragement, guidance and practical support."}, {"title": "Serve", "body": "Use your gifts to make a positive difference."}]},
				{"id": "cta-1", "type": "cta", "heading": "We would love to hear from you", "body": "Send {{business_name}} a message and our team will help.", "primary_action": {"label": "Contact us", "url": "/contact"}},
			]}],
			"integrations": {"widget_enabled": True, "whatsapp_enabled": True, "crm_enabled": True},
		},
	},
	{
		"key": "professional-v1", "name": "Professional Services", "category": "Services",
		"description": "A confident, polished layout for consultants and professional firms.",
		"definition": {
			"schema_version": 1,
			"site": {"title": "{{business_name}}", "description": "Professional {{business_nature}} expertise.", "language": "en"},
			"brand": {"primary_color": "#123f78", "secondary_color": "#0f8a78", "background_color": "#f7f9fc", "text_color": "#14213d"},
			"navigation": [{"label": "Home", "page_slug": "home"}],
			"pages": [{"slug": "home", "title": "Home", "description": "Professional expertise", "sections": [
				{"id": "hero-1", "type": "hero", "eyebrow": "Clarity. Confidence. Results.", "heading": "Move forward with {{business_name}}", "body": "Practical expertise and responsive support for important business decisions.", "primary_action": {"label": "Book a consultation", "url": "/contact"}},
				{"id": "features-1", "type": "features", "heading": "Professional support that delivers", "items": [{"title": "Practical advice", "body": "Clear recommendations you can act on."}, {"title": "Responsive service", "body": "Reliable communication throughout your engagement."}, {"title": "Measurable progress", "body": "Work focused on outcomes that matter."}]},
				{"id": "cta-1", "type": "cta", "heading": "Let us discuss your goals", "body": "Start a conversation with {{business_name}}.", "primary_action": {"label": "Talk to our team", "url": "/contact"}},
			]}],
			"integrations": {"widget_enabled": True, "whatsapp_enabled": False, "crm_enabled": True},
		},
	},
)


def _clean(value, label, maximum, required=False):
	value = " ".join(str(value or "").split())
	if required and not value:
		frappe.throw(f"{label} is required.", frappe.ValidationError)
	if len(value) > maximum:
		frappe.throw(f"{label} cannot exceed {maximum} characters.", frappe.ValidationError)
	return value


def _template_key(value):
	value = _clean(value, "Template key", 80, required=True).lower()
	if not KEY_PATTERN.fullmatch(value):
		frappe.throw("Template key must use lowercase letters, numbers, dots, hyphens or underscores.", frappe.ValidationError)
	return value


def _replace_placeholders(value, context):
	if isinstance(value, dict):
		return {key: _replace_placeholders(item, context) for key, item in value.items()}
	if isinstance(value, list):
		return [_replace_placeholders(item, context) for item in value]
	if isinstance(value, str):
		for key in PLACEHOLDERS:
			value = value.replace("{{" + key + "}}", context[key])
	return value


def _public_row(row):
	data = {
		"key": row["key"], "name": row["name"], "category": row["category"],
		"description": row["description"], "source": row["source"],
		"updated_on": row.get("updated_on"),
	}
	if "active" in row:
		data["active"] = bool(row["active"])
	return data


def catalog(include_disabled=False):
	rows = [{**item, "source": "Built-in", "updated_on": None} for item in BUILT_IN_TEMPLATES]
	if frappe.db.exists("DocType", "VerityAI Website Template"):
		filters = {} if include_disabled else {"active": 1}
		for doc in frappe.get_all("VerityAI Website Template", filters=filters, fields=["template_key", "template_name", "category", "description", "active", "modified"], order_by="template_name asc"):
			rows.append({"key": doc.template_key, "name": doc.template_name, "category": doc.category, "description": doc.description, "active": doc.active, "source": "Uploaded", "updated_on": doc.modified})
	return [_public_row(row) for row in rows]


def _template_record(template_key):
	for item in BUILT_IN_TEMPLATES:
		if item["key"] == template_key:
			return item
	name = frappe.db.get_value("VerityAI Website Template", {"template_key": template_key, "active": 1}, "name")
	if not name:
		frappe.throw("Website template was not found or is inactive.", frappe.DoesNotExistError)
	doc = frappe.get_doc("VerityAI Website Template", name)
	return {"key": doc.template_key, "name": doc.template_name, "category": doc.category, "description": doc.description, "definition": frappe.parse_json(doc.definition_json)}


def build_definition(template_key, business_name, business_nature=None):
	template_key = _template_key(template_key)
	record = _template_record(template_key)
	context = {
		"business_name": _clean(business_name, "Business name", 140, required=True),
		"business_nature": _clean(business_nature or "business", "Business nature", 140, required=True),
	}
	return validate_definition(_replace_placeholders(record["definition"], context))


def _read_manifest(uploaded_file):
	if not uploaded_file or not str(getattr(uploaded_file, "filename", "")).lower().endswith(".zip"):
		frappe.throw("Select a ZIP website-template package.", frappe.ValidationError)
	content = uploaded_file.read(MAX_ARCHIVE_BYTES + 1)
	if not content or len(content) > MAX_ARCHIVE_BYTES:
		frappe.throw("Template ZIP must be between 1 byte and 5 MB.", frappe.ValidationError)
	try:
		archive = zipfile.ZipFile(io.BytesIO(content))
	except (zipfile.BadZipFile, OSError):
		frappe.throw("The uploaded file is not a valid ZIP archive.", frappe.ValidationError)
	infos = archive.infolist()
	if not infos or len(infos) > MAX_ARCHIVE_FILES:
		frappe.throw(f"Template ZIP may contain at most {MAX_ARCHIVE_FILES} files.", frappe.ValidationError)
	total = 0
	manifest_info = None
	seen_names = set()
	for info in infos:
		name = info.filename.replace("\\", "/")
		normalized_name = name.casefold()
		parts = name.split("/")
		mode = info.external_attr >> 16
		if normalized_name in seen_names:
			frappe.throw("Template ZIP contains duplicate file names.", frappe.ValidationError)
		seen_names.add(normalized_name)
		if info.flag_bits & 0x1 or name.startswith("/") or "" in parts or ".." in parts or "\x00" in name or (mode & 0o170000) == 0o120000:
			frappe.throw("Template ZIP contains an unsafe path, encrypted file or symbolic link.", frappe.ValidationError)
		if info.is_dir():
			continue
		total += info.file_size
		if total > MAX_EXPANDED_BYTES or info.file_size > MAX_EXPANDED_BYTES:
			frappe.throw("Expanded template ZIP cannot exceed 10 MB.", frappe.ValidationError)
		if len(parts) == 1 and name.lower() in MANIFEST_NAMES:
			manifest_info = info
		elif not (name.lower() == "readme.txt" or name.lower() == "readme.md"):
			frappe.throw("Template ZIP may contain template.json and an optional README only.", frappe.ValidationError)
	if not manifest_info or manifest_info.file_size > 512 * 1024:
		frappe.throw("Template ZIP must contain a root template.json file no larger than 512 KB.", frappe.ValidationError)
	try:
		manifest = json.loads(archive.read(manifest_info).decode("utf-8"))
	except (UnicodeDecodeError, ValueError, RuntimeError):
		frappe.throw("template.json must contain valid UTF-8 JSON.", frappe.ValidationError)
	return content, manifest


def upload_package(uploaded_file, user=None):
	content, manifest = _read_manifest(uploaded_file)
	if not isinstance(manifest, dict) or set(manifest) - {"key", "name", "category", "description", "definition"}:
		frappe.throw("template.json contains unsupported fields.", frappe.ValidationError)
	key = _template_key(manifest.get("key"))
	if any(item["key"] == key for item in BUILT_IN_TEMPLATES):
		frappe.throw("Built-in template keys cannot be replaced.", frappe.ValidationError)
	name = _clean(manifest.get("name"), "Template name", 140, required=True)
	category = _clean(manifest.get("category") or "Custom", "Template category", 80, required=True)
	description = _clean(manifest.get("description"), "Template description", 500, required=True)
	definition = manifest.get("definition")
	validated_sample = validate_definition(_replace_placeholders(definition, {"business_name": "Example Business", "business_nature": "business"}))
	canonical = json.dumps(definition, separators=(",", ":"), sort_keys=True)
	archive_hash = hashlib.sha256(content).hexdigest()
	existing = frappe.db.get_value("VerityAI Website Template", {"template_key": key}, "name")
	doc = frappe.get_doc("VerityAI Website Template", existing) if existing else frappe.new_doc("VerityAI Website Template")
	doc.update({
		"template_key": key, "template_name": name, "category": category, "description": description,
		"definition_json": canonical, "definition_hash": hashlib.sha256(json.dumps(validated_sample, separators=(",", ":"), sort_keys=True).encode()).hexdigest(),
		"archive_hash": archive_hash, "active": 1, "uploaded_by_user": user or frappe.session.user,
		"uploaded_on": now_datetime(),
	})
	if existing:
		doc.save(ignore_permissions=True)
	else:
		doc.insert(ignore_permissions=True)
	file_doc = frappe.get_doc({
		"doctype": "File", "file_name": f"website-template-{key}.zip", "is_private": 1,
		"content": content, "attached_to_doctype": doc.doctype, "attached_to_name": doc.name,
		"attached_to_field": "archive_file",
	}).save(ignore_permissions=True)
	doc.db_set("archive_file", file_doc.file_url, update_modified=False)
	return {**_public_row({"key": key, "name": name, "category": category, "description": description, "source": "Uploaded", "updated_on": doc.modified}), "archive_hash": archive_hash}


def set_active(template_key, active):
	key = _template_key(template_key)
	name = frappe.db.get_value("VerityAI Website Template", {"template_key": key}, "name")
	if not name:
		frappe.throw("Uploaded website template was not found.", frappe.DoesNotExistError)
	frappe.db.set_value("VerityAI Website Template", name, "active", cint(active), update_modified=True)
	return catalog(include_disabled=True)


def validate_template_document(doc, method=None):
	doc.template_key = _template_key(doc.template_key)
	if any(item["key"] == doc.template_key for item in BUILT_IN_TEMPLATES):
		frappe.throw("Built-in template keys cannot be replaced.", frappe.ValidationError)
	doc.template_name = _clean(doc.template_name, "Template name", 140, required=True)
	doc.category = _clean(doc.category, "Template category", 80, required=True)
	doc.description = _clean(doc.description, "Template description", 500, required=True)
	definition = frappe.parse_json(doc.definition_json)
	validated = validate_definition(_replace_placeholders(definition, {"business_name": "Example Business", "business_nature": "business"}))
	doc.definition_json = json.dumps(definition, separators=(",", ":"), sort_keys=True)
	doc.definition_hash = hashlib.sha256(json.dumps(validated, separators=(",", ":"), sort_keys=True).encode()).hexdigest()
	if not re.fullmatch(r"[0-9a-f]{64}", str(doc.archive_hash or "")):
		frappe.throw("Template archive hash is invalid.", frappe.ValidationError)


def protect_template_delete(doc, method=None):
	frappe.throw("Uploaded website templates are deactivated instead of deleted.", frappe.PermissionError)
