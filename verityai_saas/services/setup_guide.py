from io import BytesIO
from pathlib import Path

import frappe
from frappe.utils import now_datetime
from frappe.utils.file_manager import save_file
from pypdf import PdfReader


ATTACHED_TO_DOCTYPE = "VerityAI Platform Settings"
ATTACHED_TO_NAME = "VerityAI Platform Settings"
ATTACHED_TO_FIELD = "whatsapp_setup_guide"
MAX_FILE_SIZE = 20 * 1024 * 1024
BLOCKED_PDF_FEATURES = (b"/JavaScript", b"/JS", b"/Launch", b"/EmbeddedFile")


def status():
	file_url = frappe.db.get_single_value(ATTACHED_TO_DOCTYPE, ATTACHED_TO_FIELD) or ""
	if not file_url:
		return {"available": False, "url": "", "file_name": "", "file_size": 0}
	rows = frappe.get_all(
		"File",
		filters={"file_url": file_url, "is_private": 0},
		fields=["name", "file_name", "file_url", "file_size", "modified"],
		order_by="creation desc",
		limit=1,
	)
	if not rows:
		return {"available": False, "url": "", "file_name": "", "file_size": 0}
	row = rows[0]
	return {
		"available": True,
		"url": row.file_url,
		"file_name": row.file_name,
		"file_size": row.file_size or 0,
		"modified": row.modified,
	}


def _validate_pdf(filename, content):
	if Path(filename or "").suffix.lower() != ".pdf":
		frappe.throw("Choose a PDF file.", frappe.ValidationError)
	if not content:
		frappe.throw("The uploaded PDF is empty.", frappe.ValidationError)
	if len(content) > MAX_FILE_SIZE:
		frappe.throw("The setup guide must be 20 MB or smaller.", frappe.ValidationError)
	if not content.startswith(b"%PDF-"):
		frappe.throw("The uploaded file is not a valid PDF.", frappe.ValidationError)
	if any(feature in content for feature in BLOCKED_PDF_FEATURES):
		frappe.throw("PDFs containing scripts, launch actions, or embedded files are not allowed.", frappe.ValidationError)
	try:
		reader = PdfReader(BytesIO(content))
		if reader.is_encrypted or not reader.pages:
			frappe.throw("Upload an unencrypted PDF containing at least one page.", frappe.ValidationError)
	except frappe.ValidationError:
		raise
	except Exception:
		frappe.throw("The uploaded PDF could not be read.", frappe.ValidationError)


def upload(uploaded_file):
	if not uploaded_file:
		frappe.throw("Select a setup-guide PDF to upload.", frappe.ValidationError)
	content = uploaded_file.read(MAX_FILE_SIZE + 1)
	_validate_pdf(uploaded_file.filename, content)
	previous_url = frappe.db.get_single_value(ATTACHED_TO_DOCTYPE, ATTACHED_TO_FIELD) or ""
	previous = frappe.db.get_value("File", {"file_url": previous_url}, "name") if previous_url else None
	stamp = now_datetime().strftime("%Y%m%d-%H%M%S")
	file_doc = save_file(
		f"veritycore-ai-whatsapp-setup-guide-{stamp}.pdf",
		content,
		ATTACHED_TO_DOCTYPE,
		ATTACHED_TO_NAME,
		is_private=0,
		df=ATTACHED_TO_FIELD,
	)
	frappe.db.set_single_value(ATTACHED_TO_DOCTYPE, ATTACHED_TO_FIELD, file_doc.file_url)
	frappe.clear_cache(doctype=ATTACHED_TO_DOCTYPE)
	if previous and previous != file_doc.name and frappe.db.exists("File", previous):
		frappe.delete_doc("File", previous, ignore_permissions=True)
	return status()
