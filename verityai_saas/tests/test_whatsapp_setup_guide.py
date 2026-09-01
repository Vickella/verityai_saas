import re
import unittest
from pathlib import Path


class TestWhatsAppSetupGuide(unittest.TestCase):
	@classmethod
	def setUpClass(cls):
		cls.repository_root = Path(__file__).resolve().parents[2]
		cls.guide_root = cls.repository_root / "verityai_saas" / "public" / "guides"
		cls.html_path = cls.guide_root / "veritycore-ai-whatsapp-setup-guide.html"
		cls.pdf_path = cls.guide_root / "veritycore-ai-whatsapp-setup-guide.pdf"

	def test_guide_assets_are_publishable(self):
		self.assertTrue(self.html_path.is_file())
		self.assertTrue(self.pdf_path.is_file())
		pdf = self.pdf_path.read_bytes()
		self.assertEqual(pdf[:8], b"%PDF-1.4")
		page_count = pdf.count(b"/Type /Page") - pdf.count(b"/Type /Pages")
		self.assertEqual(page_count, 9)
		self.assertGreater(len(pdf), 50_000)

	def test_guide_covers_the_working_inbound_flow(self):
		html = self.html_path.read_text(encoding="utf-8")
		for required_text in (
			"Publish",
			"whatsapp_business_management",
			"whatsapp_business_messaging",
			"Phone Number ID",
			"WhatsApp Business Account ID",
			"Verify every Meta webhook signature",
			"messages",
			"Subscribe WABA",
			"Receiving",
			"Healthy",
		):
			self.assertIn(required_text, html)

	def test_guide_contains_no_customer_credentials(self):
		html = self.html_path.read_text(encoding="utf-8")
		self.assertIsNone(re.search(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", html))
		self.assertIsNone(re.search(r"\b\d{13,}\b", html))
		self.assertIsNone(re.search(r"EAA[A-Za-z0-9]{20,}", html))
		self.assertIn('class="input secret"', html)

	def test_whatsapp_page_links_to_the_pdf(self):
		portal_js = (
			self.repository_root / "verityai_saas" / "public" / "js" / "portal.js"
		).read_text(encoding="utf-8")
		self.assertIn(
			'/assets/verityai_saas/guides/veritycore-ai-whatsapp-setup-guide.pdf',
			portal_js,
		)


if __name__ == "__main__":
	unittest.main()
