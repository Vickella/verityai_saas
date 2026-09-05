import hashlib
import json
import re
from urllib.parse import urlsplit

import frappe


SCHEMA_VERSION = 1
MAX_DEFINITION_BYTES = 256 * 1024
MAX_PAGES = 10
MAX_SECTIONS_PER_PAGE = 30
MAX_ITEMS_PER_SECTION = 12
SECTION_TYPES = {"hero", "text", "features", "cta", "testimonials", "contact", "faq", "gallery"}
TOP_LEVEL_FIELDS = {"schema_version", "site", "brand", "navigation", "pages", "integrations"}
SITE_FIELDS = {"title", "description", "language"}
BRAND_FIELDS = {"primary_color", "secondary_color", "background_color", "text_color", "logo_url"}
PAGE_FIELDS = {"slug", "title", "description", "sections"}
SECTION_FIELDS = {"id", "type", "eyebrow", "heading", "body", "image_url", "alt_text", "items", "primary_action", "secondary_action"}
ITEM_FIELDS = {"title", "body", "label", "icon", "image_url", "alt_text", "url"}
ACTION_FIELDS = {"label", "url"}
INTEGRATION_FIELDS = {"widget_enabled", "whatsapp_enabled", "crm_enabled"}
SLUG_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
COLOR_PATTERN = re.compile(r"^#[0-9a-fA-F]{6}$")
HTML_PATTERN = re.compile(r"<[^>]+>|javascript\s*:|data\s*:\s*text/html|on[a-z]+\s*=", re.IGNORECASE)


def _fail(message):
	frappe.throw(message, frappe.ValidationError)


def _object(value, label, allowed, required=False):
	if value is None and not required:
		return {}
	if not isinstance(value, dict):
		_fail(f"{label} must be an object.")
	unknown = set(value) - allowed
	if unknown:
		_fail(f"{label} contains unsupported fields: {', '.join(sorted(unknown))}.")
	return value


def _text(value, label, maximum=2000, required=False):
	value = str(value or "").strip()
	if required and not value:
		_fail(f"{label} is required.")
	if len(value) > maximum:
		_fail(f"{label} cannot exceed {maximum} characters.")
	if HTML_PATTERN.search(value):
		_fail(f"{label} cannot contain HTML or executable content.")
	return value


def _slug(value, label="Page slug"):
	value = _text(value, label, 80, required=True).lower()
	if not SLUG_PATTERN.fullmatch(value):
		_fail(f"{label} must contain lowercase letters, numbers and single hyphens only.")
	return value


def _url(value, label, image=False):
	value = _text(value, label, 1000)
	if not value:
		return ""
	if value.startswith("/files/"):
		return value
	if not image and value.startswith("/") and not value.startswith("//") and "\\" not in value:
		return value
	parsed = urlsplit(value)
	allowed = {"https"} if image else {"https", "mailto", "tel"}
	if parsed.scheme not in allowed or (parsed.scheme == "https" and (not parsed.netloc or parsed.username or parsed.password)):
		_fail(f"{label} must use an approved HTTPS, mailto or tel URL.")
	return value


def _boolean(value, label):
	if value in (True, False, 0, 1, None):
		return bool(value)
	_fail(f"{label} must be true or false.")


def _action(value, label):
	if value in (None, ""):
		return None
	value = _object(value, label, ACTION_FIELDS, required=True)
	return {"label": _text(value.get("label"), f"{label} label", 80, required=True), "url": _url(value.get("url"), f"{label} URL")}


def _item(value, label):
	value = _object(value, label, ITEM_FIELDS, required=True)
	result = {}
	for key in ("title", "body", "label", "icon", "alt_text"):
		if key in value:
			result[key] = _text(value.get(key), f"{label} {key.replace('_', ' ')}", 2000 if key == "body" else 200)
	if value.get("image_url"):
		result["image_url"] = _url(value.get("image_url"), f"{label} image URL", image=True)
	if value.get("url"):
		result["url"] = _url(value.get("url"), f"{label} URL")
	return result


def _section(value, page_slug, position):
	label = f"Section {position} on {page_slug}"
	value = _object(value, label, SECTION_FIELDS, required=True)
	section_type = _text(value.get("type"), f"{label} type", 40, required=True).lower()
	if section_type not in SECTION_TYPES:
		_fail(f"{label} has an unsupported section type.")
	result = {"id": _slug(value.get("id") or f"{section_type}-{position}", f"{label} ID"), "type": section_type}
	for key in ("eyebrow", "heading", "body", "alt_text"):
		if key in value:
			result[key] = _text(value.get(key), f"{label} {key.replace('_', ' ')}", 5000 if key == "body" else 300)
	if value.get("image_url"):
		result["image_url"] = _url(value.get("image_url"), f"{label} image URL", image=True)
	items = value.get("items") or []
	if not isinstance(items, list) or len(items) > MAX_ITEMS_PER_SECTION:
		_fail(f"{label} items must be a list of at most {MAX_ITEMS_PER_SECTION} entries.")
	if items:
		result["items"] = [_item(item, f"{label} item {index}") for index, item in enumerate(items, 1)]
	for key in ("primary_action", "secondary_action"):
		action = _action(value.get(key), f"{label} {key.replace('_', ' ')}")
		if action:
			result[key] = action
	if section_type in {"hero", "cta"} and not result.get("heading"):
		_fail(f"{label} requires a heading.")
	return result


def validate_definition(value):
	if isinstance(value, str):
		try:
			value = json.loads(value)
		except (TypeError, ValueError):
			_fail("Website definition must be valid JSON.")
	value = _object(value, "Website definition", TOP_LEVEL_FIELDS, required=True)
	if int(value.get("schema_version") or SCHEMA_VERSION) != SCHEMA_VERSION:
		_fail(f"Only website schema version {SCHEMA_VERSION} is supported.")

	site = _object(value.get("site"), "Site", SITE_FIELDS, required=True)
	brand = _object(value.get("brand"), "Brand", BRAND_FIELDS)
	result = {
		"schema_version": SCHEMA_VERSION,
		"site": {
			"title": _text(site.get("title"), "Site title", 140, required=True),
			"description": _text(site.get("description"), "Site description", 500),
			"language": _text(site.get("language") or "en", "Site language", 12, required=True).lower(),
		},
		"brand": {},
	}
	for key in ("primary_color", "secondary_color", "background_color", "text_color"):
		if brand.get(key):
			color = _text(brand.get(key), key.replace("_", " ").title(), 7)
			if not COLOR_PATTERN.fullmatch(color):
				_fail(f"{key.replace('_', ' ').title()} must be a six-digit hex colour.")
			result["brand"][key] = color.lower()
	if brand.get("logo_url"):
		result["brand"]["logo_url"] = _url(brand.get("logo_url"), "Logo URL", image=True)

	pages = value.get("pages")
	if not isinstance(pages, list) or not pages or len(pages) > MAX_PAGES:
		_fail(f"Pages must contain between 1 and {MAX_PAGES} entries.")
	result["pages"] = []
	page_slugs = set()
	for index, page in enumerate(pages, 1):
		page = _object(page, f"Page {index}", PAGE_FIELDS, required=True)
		slug = _slug(page.get("slug"), f"Page {index} slug")
		if slug in page_slugs:
			_fail(f"Page slug {slug} is duplicated.")
		page_slugs.add(slug)
		sections = page.get("sections")
		if not isinstance(sections, list) or not sections or len(sections) > MAX_SECTIONS_PER_PAGE:
			_fail(f"Page {slug} must contain between 1 and {MAX_SECTIONS_PER_PAGE} sections.")
		normalized_sections = [_section(section, slug, position) for position, section in enumerate(sections, 1)]
		if len({section["id"] for section in normalized_sections}) != len(normalized_sections):
			_fail(f"Page {slug} contains duplicate section IDs.")
		result["pages"].append({
			"slug": slug,
			"title": _text(page.get("title"), f"Page {slug} title", 140, required=True),
			"description": _text(page.get("description"), f"Page {slug} description", 500),
			"sections": normalized_sections,
		})
	if "home" not in page_slugs:
		_fail("Website definition must include a home page.")

	navigation = value.get("navigation") or []
	if not isinstance(navigation, list) or len(navigation) > MAX_PAGES:
		_fail(f"Navigation must be a list of at most {MAX_PAGES} entries.")
	result["navigation"] = []
	for index, item in enumerate(navigation, 1):
		item = _object(item, f"Navigation item {index}", {"label", "page_slug"}, required=True)
		page_slug = _slug(item.get("page_slug"), f"Navigation item {index} page slug")
		if page_slug not in page_slugs:
			_fail(f"Navigation item {index} references an unknown page.")
		result["navigation"].append({"label": _text(item.get("label"), f"Navigation item {index} label", 80, required=True), "page_slug": page_slug})

	integrations = _object(value.get("integrations"), "Integrations", INTEGRATION_FIELDS)
	result["integrations"] = {key: _boolean(integrations.get(key), key.replace("_", " ").title()) for key in INTEGRATION_FIELDS}
	payload = json.dumps(result, separators=(",", ":"), sort_keys=True)
	if len(payload.encode("utf-8")) > MAX_DEFINITION_BYTES:
		_fail(f"Website definition cannot exceed {MAX_DEFINITION_BYTES // 1024} KB.")
	return result


def canonical_json(value):
	return json.dumps(validate_definition(value), separators=(",", ":"), sort_keys=True)


def definition_hash(value):
	payload = value if isinstance(value, str) else canonical_json(value)
	return hashlib.sha256(payload.encode("utf-8")).hexdigest()
