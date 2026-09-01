import unittest
from pathlib import Path


class TestWhatsAppSetupGuide(unittest.TestCase):
	@classmethod
	def setUpClass(cls):
		cls.repository_root = Path(__file__).resolve().parents[2]
		cls.package_root = cls.repository_root / "verityai_saas"

	def test_customer_guide_is_not_bundled_with_source(self):
		guide_root = self.package_root / "public" / "guides"
		self.assertFalse(guide_root.exists())

	def test_customer_download_uses_uploaded_file_url(self):
		portal_js = (self.package_root / "public" / "js" / "portal.js").read_text(encoding="utf-8")
		self.assertIn("d.setup_guide", portal_js)
		self.assertIn("guide.available&&guide.url", portal_js)
		self.assertNotIn("/assets/verityai_saas/guides/", portal_js)

	def test_operator_console_has_pdf_upload_flow(self):
		admin_js = (self.package_root / "public" / "js" / "admin.js").read_text(encoding="utf-8")
		self.assertIn('accept="application/pdf,.pdf"', admin_js)
		self.assertIn("upload_whatsapp_setup_guide", admin_js)
		self.assertIn('["guides","Guides"]', admin_js)

	def test_upload_service_enforces_security_boundaries(self):
		service = (self.package_root / "services" / "setup_guide.py").read_text(encoding="utf-8")
		self.assertIn("MAX_FILE_SIZE = 20 * 1024 * 1024", service)
		self.assertIn('content.startswith(b"%PDF-")', service)
		self.assertIn('b"/JavaScript"', service)
		self.assertIn("reader.is_encrypted", service)
		self.assertIn("is_private=0", service)
		self.assertIn("set_single_value", service)

	def test_install_adds_the_platform_guide_attachment_field(self):
		setup = (self.package_root / "setup_doctypes.py").read_text(encoding="utf-8")
		patches = (self.package_root / "patches.txt").read_text(encoding="utf-8")
		self.assertIn('field("whatsapp_setup_guide", "WhatsApp Setup Guide", "Attach")', setup)
		self.assertIn("v0_21.whatsapp_setup_guide_upload", patches)

	def test_upload_api_requires_platform_admin_and_reauthentication(self):
		admin_api = (self.package_root / "api" / "admin.py").read_text(encoding="utf-8")
		start = admin_api.index("def upload_whatsapp_setup_guide")
		body = admin_api[start:start + 500]
		self.assertIn("require_platform_admin()", body)
		self.assertIn("require_admin_reauthentication()", body)


if __name__ == "__main__":
	unittest.main()
