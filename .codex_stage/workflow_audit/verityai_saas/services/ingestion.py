import hashlib
import ipaddress
import json
import mimetypes
import socket
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser

import frappe
import requests
from frappe.utils import add_days, cint, now_datetime

from verityai_saas.services import engine
from verityai_saas.services.permissions import is_operator


ALLOWED_EXTENSIONS = {".txt", ".md", ".csv", ".json", ".html", ".htm", ".pdf", ".docx", ".png", ".jpg", ".jpeg"}
NON_DOCUMENT_EXTENSIONS = {"avif", "bmp", "css", "gif", "ico", "jpeg", "jpg", "js", "map", "mp3", "mp4", "ogg", "png", "svg", "webm", "webp", "woff", "woff2", "zip"}
MAX_FILE_BYTES = 10 * 1024 * 1024
MAX_FETCH_BYTES = 2 * 1024 * 1024
MAX_CONTENT_CHARS = 2_000_000
USER_AGENT = "VerityAI-KnowledgeBot/1.0"


class PageParser(HTMLParser):
	def __init__(self):
		super().__init__()
		self.text = []
		self.links = []
		self.ignored = 0

	def handle_starttag(self, tag, attrs):
		if tag in {"script", "style", "noscript", "svg"}:
			self.ignored += 1
		if tag == "a" and not self.ignored:
			href = dict(attrs).get("href")
			if href:
				self.links.append(href)

	def handle_endtag(self, tag):
		if tag in {"script", "style", "noscript", "svg"} and self.ignored:
			self.ignored -= 1

	def handle_data(self, data):
		if not self.ignored and data.strip():
			self.text.append(data.strip())


def _limits(name, default):
	return max(cint(frappe.conf.get(name) or default), 1)


def _validate_public_url(url):
	parsed = urlparse((url or "").strip())
	if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
		frappe.throw("Enter a public HTTP or HTTPS URL without embedded credentials.", frappe.ValidationError)
	if parsed.port and parsed.port not in {80, 443}:
		frappe.throw("Only standard HTTP and HTTPS ports are allowed.", frappe.ValidationError)
	try:
		addresses = {item[4][0] for item in socket.getaddrinfo(parsed.hostname, parsed.port or (443 if parsed.scheme == "https" else 80), type=socket.SOCK_STREAM)}
	except OSError:
		frappe.throw("The website hostname could not be resolved.", frappe.ValidationError)
	for address in addresses:
		ip = ipaddress.ip_address(address)
		if not ip.is_global:
			frappe.throw("Private, local, reserved, and non-public website addresses are not allowed.", frappe.PermissionError)
	return parsed.geturl()


def _fetch(url, allowed_types=("text/html", "text/plain", "application/xhtml+xml")):
	session = requests.Session()
	session.trust_env = False
	current = _validate_public_url(url)
	redirects = set()
	for _ in range(8):
		if current in redirects:
			frappe.throw("Website redirect loop detected.", frappe.ValidationError)
		redirects.add(current)
		response = session.get(current, headers={"User-Agent": USER_AGENT, "Accept": ", ".join(allowed_types)}, timeout=(5, 20), allow_redirects=False, stream=True)
		if response.is_redirect or response.is_permanent_redirect:
			location = response.headers.get("Location")
			if not location:
				frappe.throw("Website redirect did not include a destination.", frappe.ValidationError)
			current = _validate_public_url(urljoin(current, location))
			continue
		response.raise_for_status()
		content_type = (response.headers.get("Content-Type") or "").split(";", 1)[0].lower()
		if content_type not in allowed_types:
			frappe.throw(f"Unsupported website content type: {content_type or 'unknown'}.", frappe.ValidationError)
		maximum = _limits("verityai_max_fetch_bytes", MAX_FETCH_BYTES)
		chunks, total = [], 0
		for chunk in response.iter_content(65536):
			total += len(chunk)
			if total > maximum:
				frappe.throw("Website content exceeds the configured ingestion size limit.", frappe.ValidationError)
			chunks.append(chunk)
		encoding = response.encoding or "utf-8"
		return current, b"".join(chunks).decode(encoding, errors="replace"), content_type, total
	frappe.throw("Website redirected too many times.", frappe.ValidationError)


def _robots_allows(url):
	parsed = urlparse(url)
	robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
	try:
		_, text, _, _ = _fetch(robots_url, allowed_types=("text/plain", "text/html"))
	except Exception:
		return True
	parser = RobotFileParser()
	parser.set_url(robots_url)
	parser.parse(text.splitlines())
	return parser.can_fetch(USER_AGENT, url)


def crawl_url(url, max_pages=None):
	start = _validate_public_url(url)
	if not _robots_allows(start):
		frappe.throw("This website disallows automated access in robots.txt.", frappe.PermissionError)
	max_pages = min(max(cint(max_pages or frappe.conf.get("verityai_max_crawl_pages") or 5), 1), 25)
	origin = (urlparse(start).scheme, urlparse(start).netloc.lower())
	queue, seen, documents, total_bytes = [start], set(), [], 0
	while queue and len(documents) < max_pages:
		candidate = queue.pop(0).split("#", 1)[0]
		if candidate in seen:
			continue
		seen.add(candidate)
		try:
			final_url, raw, content_type, size = _fetch(candidate)
		except (requests.RequestException, frappe.ValidationError, frappe.PermissionError):
			if not documents and candidate == start:
				raise
			continue
		if (urlparse(final_url).scheme, urlparse(final_url).netloc.lower()) != origin:
			continue
		total_bytes += size
		if content_type in {"text/html", "application/xhtml+xml"}:
			parser = PageParser()
			parser.feed(raw)
			text = "\n".join(parser.text)
			for link in parser.links:
				next_url = urljoin(final_url, link).split("#", 1)[0]
				parsed = urlparse(next_url)
				extension = parsed.path.lower().rsplit(".", 1)[-1] if "." in parsed.path.rsplit("/", 1)[-1] else ""
				if (parsed.scheme, parsed.netloc.lower()) == origin and extension not in NON_DOCUMENT_EXTENSIONS:
					queue.append(next_url)
		else:
			text = raw
		if text.strip():
			documents.append(f"Source: {final_url}\n{text.strip()}")
	if not documents:
		frappe.throw("No readable website text was found.", frappe.ValidationError)
	return "\n\n".join(documents)[:MAX_CONTENT_CHARS], len(documents), total_bytes


def _extract_pdf(path):
	try:
		from pypdf import PdfReader
	except ImportError:
		from PyPDF2 import PdfReader
	reader = PdfReader(str(path))
	text = "\n".join((page.extract_text() or "") for page in reader.pages)
	if text.strip():
		return text, len(reader.pages)
	try:
		from pdf2image import convert_from_path
		import pytesseract
		images = convert_from_path(str(path), first_page=1, last_page=min(len(reader.pages), 20))
		return "\n".join(pytesseract.image_to_string(image) for image in images), len(images)
	except ImportError:
		frappe.throw("The PDF has no extractable text. Install pdf2image and pytesseract to enable OCR.", frappe.ValidationError)


def extract_file(file_name):
	file_doc = frappe.get_doc("File", file_name)
	if not file_doc.is_private:
		frappe.throw("Knowledge files must be uploaded as private files.", frappe.PermissionError)
	if not is_operator() and file_doc.owner != frappe.session.user:
		frappe.throw("You can only ingest files you uploaded.", frappe.PermissionError)
	path = Path(file_doc.get_full_path()).resolve()
	extension = path.suffix.lower()
	if extension not in ALLOWED_EXTENSIONS:
		frappe.throw("Unsupported file type. Use TXT, Markdown, CSV, JSON, HTML, PDF, DOCX, PNG, or JPEG.", frappe.ValidationError)
	size = path.stat().st_size
	if size > _limits("verityai_max_knowledge_file_bytes", MAX_FILE_BYTES):
		frappe.throw("Knowledge file exceeds the configured size limit.", frappe.ValidationError)
	pages = 1
	if extension in {".txt", ".md", ".csv", ".json"}:
		content = path.read_text(encoding="utf-8", errors="replace")
	elif extension in {".html", ".htm"}:
		parser = PageParser()
		parser.feed(path.read_text(encoding="utf-8", errors="replace"))
		content = "\n".join(parser.text)
	elif extension == ".pdf":
		content, pages = _extract_pdf(path)
	elif extension == ".docx":
		try:
			from docx import Document
		except ImportError:
			frappe.throw("Install python-docx to ingest DOCX files.", frappe.ValidationError)
		document = Document(str(path))
		content = "\n".join(paragraph.text for paragraph in document.paragraphs)
	else:
		try:
			from PIL import Image
			import pytesseract
		except ImportError:
			frappe.throw("Install Pillow and pytesseract to OCR image files.", frappe.ValidationError)
		content = pytesseract.image_to_string(Image.open(path))
	if not content.strip():
		frappe.throw("No readable text was extracted from the file.", frappe.ValidationError)
	return content[:MAX_CONTENT_CHARS], pages, size, file_doc.file_url


def _check_capacity(workspace_name):
	frappe.db.sql("select name from `tabVerityAI Workspace` where name=%s for update", workspace_name)
	context_plan = frappe.db.get_value("VerityAI Subscription", {"workspace": workspace_name, "status": ["in", ["Trial", "Active", "Past Due"]]}, "plan", order_by="creation desc")
	limit = cint(frappe.db.get_value("VerityAI Plan", context_plan, "max_knowledge_sources")) if context_plan else 0
	if not limit:
		return
	tenant = engine.get_workspace_engine_tenant(workspace_name)
	existing = frappe.db.count("AI Knowledge Source", {"tenant": tenant})
	pending = frappe.db.count("VerityAI Knowledge Ingestion", {"workspace": workspace_name, "knowledge_source": ["is", "not set"], "status": ["in", ["Pending", "Processing"]]})
	if existing + pending >= limit:
		frappe.throw("Your knowledge source plan limit has been reached.", frappe.ValidationError)


def queue_ingestion(workspace_name, title, source_type, source_url=None, file_name=None):
	_check_capacity(workspace_name)
	if source_type not in {"File", "URL"}:
		frappe.throw("Queued ingestion supports File or URL sources.", frappe.ValidationError)
	if not (title or "").strip():
		frappe.throw("Knowledge title is required.", frappe.ValidationError)
	file_url = None
	if source_type == "File":
		file_doc = frappe.get_doc("File", file_name)
		if not file_doc.is_private or (not is_operator() and file_doc.owner != frappe.session.user):
			frappe.throw("Select a private file that you uploaded.", frappe.PermissionError)
		file_url = file_doc.file_url
	else:
		source_url = _validate_public_url(source_url)
	doc = frappe.get_doc({"doctype": "VerityAI Knowledge Ingestion", "workspace": workspace_name, "title": title.strip(), "source_type": source_type, "source_url": source_url, "file_url": file_url, "status": "Pending"}).insert(ignore_permissions=True)
	frappe.enqueue("verityai_saas.services.ingestion.process_ingestion", queue="long", enqueue_after_commit=True, ingestion_name=doc.name, file_name=file_name)
	return doc.name


def process_ingestion(ingestion_name, file_name=None):
	doc = frappe.get_doc("VerityAI Knowledge Ingestion", ingestion_name)
	doc.status, doc.error = "Processing", None
	doc.save(ignore_permissions=True)
	try:
		if doc.source_type == "URL":
			content, pages, size = crawl_url(doc.source_url)
		else:
			if not file_name:
				file_name = frappe.db.get_value("File", {"file_url": doc.file_url, "is_private": 1}, "name")
			content, pages, size, _ = extract_file(file_name)
		content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
		duplicate = frappe.db.get_value("VerityAI Knowledge Ingestion", {"workspace": doc.workspace, "content_hash": content_hash, "status": "Ready", "name": ["!=", doc.name]}, "name")
		if duplicate:
			frappe.throw("This knowledge content has already been ingested.", frappe.DuplicateEntryError)
		if doc.knowledge_source:
			engine.update_knowledge_source(doc.workspace, doc.knowledge_source, {"title": doc.title, "content": content, "active": 1})
			source = doc.knowledge_source
		else:
			source = engine.create_knowledge_source(doc.workspace, doc.title, content, doc.file_url)
		doc.update({"knowledge_source": source, "status": "Ready", "content_hash": content_hash, "pages_processed": pages, "bytes_processed": size, "last_refreshed_on": now_datetime(), "next_refresh_on": add_days(now_datetime(), 30) if doc.source_type == "URL" else None, "error": None})
	except Exception as exc:
		doc.status = "Failed"
		doc.error = str(exc)[:1000]
		doc.save(ignore_permissions=True)
		frappe.db.commit()
		raise
	doc.save(ignore_permissions=True)
	frappe.db.commit()
	return doc.name


def refresh_ingestion(workspace_name, ingestion_name):
	if not frappe.db.exists("VerityAI Knowledge Ingestion", {"name": ingestion_name, "workspace": workspace_name, "source_type": "URL"}):
		frappe.throw("Refreshable URL ingestion was not found.", frappe.DoesNotExistError)
	frappe.db.set_value("VerityAI Knowledge Ingestion", ingestion_name, {"status": "Pending", "error": None})
	frappe.enqueue("verityai_saas.services.ingestion.process_ingestion", queue="long", enqueue_after_commit=True, ingestion_name=ingestion_name)
	return ingestion_name


def update_ingestion(workspace_name, ingestion_name, values):
	if not frappe.db.exists("VerityAI Knowledge Ingestion", {"name": ingestion_name, "workspace": workspace_name}):
		frappe.throw("Knowledge processing record was not found.", frappe.DoesNotExistError)
	doc = frappe.get_doc("VerityAI Knowledge Ingestion", ingestion_name)
	if doc.status == "Processing":
		frappe.throw("Wait for processing to finish before editing this source.", frappe.ValidationError)
	was_pending = doc.status == "Pending"
	title = str(values.get("title") or "").strip()
	if not title:
		frappe.throw("A knowledge source title is required.", frappe.ValidationError)
	doc.title = title
	refresh = False
	if doc.source_type == "URL":
		source_url = _validate_public_url(values.get("source_url") or doc.source_url)
		refresh = source_url != doc.source_url or cint(values.get("refresh"))
		doc.source_url = source_url
	if doc.knowledge_source:
		source_values = {"title": title}
		if doc.source_type == "Text" and "content" in values:
			source_values["content"] = values.get("content")
		if "active" in values:
			source_values["active"] = values.get("active")
		engine.update_knowledge_source(workspace_name, doc.knowledge_source, source_values)
	if doc.source_type == "Text" and "content" in values:
		content = str(values.get("content") or "").strip()
		doc.content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
		doc.bytes_processed = len(content.encode("utf-8"))
		doc.pages_processed = 1
		doc.last_refreshed_on = now_datetime()
		doc.status = "Ready"
		doc.error = None
	if refresh:
		doc.status = "Pending"
		doc.error = None
	doc.save(ignore_permissions=True)
	if refresh and not was_pending:
		frappe.enqueue(
			"verityai_saas.services.ingestion.process_ingestion",
			queue="long",
			enqueue_after_commit=True,
			ingestion_name=doc.name,
		)
	return {
		"name": doc.name,
		"knowledge_source": doc.knowledge_source,
		"title": doc.title,
		"source_type": doc.source_type,
		"source_url": doc.source_url,
		"status": doc.status,
	}


def list_ingestions(workspace_name):
	return frappe.get_all("VerityAI Knowledge Ingestion", filters={"workspace": workspace_name}, fields=["name", "knowledge_source", "title", "source_type", "source_url", "file_url", "status", "pages_processed", "bytes_processed", "last_refreshed_on", "next_refresh_on", "error", "creation", "modified"], order_by="creation desc", limit=200)


def delete_ingestion(workspace_name, ingestion_name):
	if not frappe.db.exists("VerityAI Knowledge Ingestion", {"name": ingestion_name, "workspace": workspace_name}):
		frappe.throw("Knowledge processing record was not found.", frappe.DoesNotExistError)
	doc = frappe.get_doc("VerityAI Knowledge Ingestion", ingestion_name)
	if doc.status == "Processing":
		frappe.throw("Wait for processing to finish before deleting this record.", frappe.ValidationError)
	frappe.delete_doc("VerityAI Knowledge Ingestion", ingestion_name, ignore_permissions=True, force=True)
	return {"deleted": ingestion_name}
