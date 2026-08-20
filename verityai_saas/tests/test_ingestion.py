from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils.file_manager import save_file

from verityai_saas import setup_doctypes
from verityai_saas.api import knowledge as knowledge_api
from verityai_saas.services import ingestion
from verityai_saas.services.onboarding import create_workspace
from verityai_saas.tests.cleanup import cleanup_all_test_fixtures, cleanup_test_workspace


class TestKnowledgeIngestion(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		frappe.set_user("Administrator")
		setup_doctypes.install()

	@classmethod
	def tearDownClass(cls):
		super().tearDownClass()
		cleanup_all_test_fixtures()

	def setUp(self):
		frappe.set_user("Administrator")
		token = frappe.generate_hash(length=8).lower()
		self.owner = frappe.get_doc({"doctype": "User", "email": f"ingest-owner-{token}@example.com", "first_name": "Ingestion", "last_name": "Owner", "user_type": "Website User", "send_welcome_email": 0}).insert(ignore_permissions=True).name
		self.created = create_workspace(self.owner, f"Ingestion Account {token}", f"Ingestion Workspace {token}")
		self.workspace = self.created["workspace"]
		self.tenant = self.created["engine_tenant"]
		self.files = []

	def tearDown(self):
		frappe.set_user("Administrator")
		for name in self.files:
			if frappe.db.exists("File", name):
				frappe.delete_doc("File", name, ignore_permissions=True, force=True)
		cleanup_test_workspace(self.workspace, users=[self.owner], engine_tenant=self.tenant)

	def test_private_text_file_is_queued_extracted_and_indexed(self):
		frappe.set_user(self.owner)
		file_doc = save_file("knowledge.txt", b"Our support hours are Monday to Friday.", None, None, is_private=1)
		self.files.append(file_doc.name)
		with patch("frappe.enqueue") as enqueue:
			response = knowledge_api.ingest_file(self.workspace, "Support Hours", file_doc.name)
		self.assertTrue(response["success"])
		ingestion_name = response["data"]["ingestion"]
		enqueue.assert_called_once()
		ingestion.process_ingestion(ingestion_name, file_doc.name)
		status = frappe.get_doc("VerityAI Knowledge Ingestion", ingestion_name)
		self.assertEqual(status.status, "Ready")
		self.assertTrue(status.knowledge_source)
		self.assertGreater(frappe.db.count("AI Knowledge Chunk", {"knowledge_source": status.knowledge_source}), 0)

	def test_public_url_ingestion_refreshes_engine_source(self):
		frappe.set_user(self.owner)
		with patch("verityai_saas.services.ingestion._validate_public_url", side_effect=lambda url: url), patch("frappe.enqueue"):
			response = knowledge_api.ingest_url(self.workspace, "Website", "https://example.com/docs")
		ingestion_name = response["data"]["ingestion"]
		with patch("verityai_saas.services.ingestion.crawl_url", return_value=("First website content", 1, 21)):
			ingestion.process_ingestion(ingestion_name)
		source = frappe.db.get_value("VerityAI Knowledge Ingestion", ingestion_name, "knowledge_source")
		with patch("frappe.enqueue") as enqueue:
			refreshed = knowledge_api.refresh(self.workspace, ingestion_name)
		self.assertTrue(refreshed["success"])
		enqueue.assert_called_once()
		with patch("verityai_saas.services.ingestion.crawl_url", return_value=("Updated website content", 1, 23)):
			ingestion.process_ingestion(ingestion_name)
		self.assertEqual(frappe.db.get_value("AI Knowledge Source", source, "content"), "Updated website content")

	def test_crawl_skips_discovered_webp_and_keeps_page_text(self):
		def fetch(url, allowed_types=("text/html", "text/plain", "application/xhtml+xml")):
			if url.endswith("/image"):
				raise frappe.ValidationError("Unsupported website content type: image/webp.")
			return url, '<html><body><h1>Useful service knowledge</h1><a href="/image">Image</a></body></html>', "text/html", 85

		with patch("verityai_saas.services.ingestion._validate_public_url", side_effect=lambda url: url), patch("verityai_saas.services.ingestion._robots_allows", return_value=True), patch("verityai_saas.services.ingestion._fetch", side_effect=fetch):
			content, pages, _ = ingestion.crawl_url("https://example.com", max_pages=5)
		self.assertIn("Useful service knowledge", content)
		self.assertEqual(pages, 1)

	def test_workspace_owner_can_delete_source_and_index(self):
		frappe.set_user(self.owner)
		response = knowledge_api.create(self.workspace, "Temporary", "Temporary knowledge for deletion")
		source = response["data"]["source"]
		self.assertTrue(frappe.db.exists("AI Knowledge Source", source))
		self.assertGreater(frappe.db.count("AI Knowledge Chunk", {"knowledge_source": source}), 0)
		deleted = knowledge_api.delete(self.workspace, source)
		self.assertTrue(deleted["success"])
		self.assertFalse(frappe.db.exists("AI Knowledge Source", source))
		self.assertFalse(frappe.db.exists("AI Knowledge Chunk", {"knowledge_source": source}))

	def test_private_and_loopback_urls_are_rejected(self):
		with patch("socket.getaddrinfo", return_value=[(2, 1, 6, "", ("127.0.0.1", 80))]):
			with self.assertRaises(frappe.PermissionError):
				ingestion._validate_public_url("http://localhost")
		with self.assertRaises(frappe.ValidationError):
			ingestion._validate_public_url("file:///etc/passwd")

	def test_duplicate_content_is_rejected_without_second_source(self):
		frappe.set_user(self.owner)
		with patch("verityai_saas.services.ingestion._validate_public_url", side_effect=lambda url: url), patch("frappe.enqueue"):
			first = knowledge_api.ingest_url(self.workspace, "First", "https://example.com/one")["data"]["ingestion"]
			second = knowledge_api.ingest_url(self.workspace, "Second", "https://example.com/two")["data"]["ingestion"]
		with patch("verityai_saas.services.ingestion.crawl_url", return_value=("Same content", 1, 12)):
			ingestion.process_ingestion(first)
			with self.assertRaises(frappe.DuplicateEntryError):
				ingestion.process_ingestion(second)
		self.assertEqual(frappe.db.get_value("VerityAI Knowledge Ingestion", second, "status"), "Failed")

	def test_owner_can_delete_finished_processing_record_only_in_own_workspace(self):
		frappe.set_user(self.owner)
		with patch("verityai_saas.services.ingestion._validate_public_url", side_effect=lambda url: url), patch("frappe.enqueue"):
			ingestion_name = knowledge_api.ingest_url(self.workspace, "Disposable", "https://example.com/delete")["data"]["ingestion"]
		deleted = knowledge_api.delete_processing(self.workspace, ingestion_name)
		self.assertTrue(deleted["success"])
		self.assertFalse(frappe.db.exists("VerityAI Knowledge Ingestion", ingestion_name))

	def test_processing_record_cannot_be_deleted_while_running(self):
		frappe.set_user(self.owner)
		with patch("verityai_saas.services.ingestion._validate_public_url", side_effect=lambda url: url), patch("frappe.enqueue"):
			ingestion_name = knowledge_api.ingest_url(self.workspace, "Running", "https://example.com/running")["data"]["ingestion"]
		frappe.db.set_value("VerityAI Knowledge Ingestion", ingestion_name, "status", "Processing")
		response = knowledge_api.delete_processing(self.workspace, ingestion_name)
		self.assertFalse(response["success"])
		self.assertEqual(response["code"], "VALIDATION_ERROR")
