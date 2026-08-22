import json
import mimetypes
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

WEBSITE_ROOT = Path(r"C:\Users\havano\Documents\vt\saas_ai_website")
ENGINE_ROOT = Path(r"C:\Users\havano\Documents\vt\verity_ai\verity_ai\public")
SITE_ORIGIN = "http://127.0.0.1:4183"
API_ORIGIN = "http://127.0.0.1:4184"


class BaseHandler(BaseHTTPRequestHandler):
	def send_bytes(self, body, content_type, status=200, headers=None):
		self.send_response(status)
		self.send_header("Content-Type", content_type)
		self.send_header("Cache-Control", "no-store")
		for key, value in (headers or {}).items():
			self.send_header(key, value)
		self.end_headers()
		self.wfile.write(body)

	def log_message(self, *_args):
		return


class SiteHandler(BaseHandler):
	def do_GET(self):
		path = urlparse(self.path).path
		if path in ("/", "/index.html"):
			html = (WEBSITE_ROOT / "index.html").read_text(encoding="utf-8")
			html = html.replace(
				'https://saasai.veritypack.cloud/assets/verity_ai/js/widget.js?v=20260817',
				f'{API_ORIGIN}/widget.js?v=20260817',
			)
			html = html.replace("</body>", '<script>setTimeout(()=>document.getElementById("verity-fab")?.click(),700)</script></body>')
			return self.send_bytes(html.encode(), "text/html; charset=utf-8")
		candidate = (WEBSITE_ROOT / path.lstrip("/")).resolve()
		if WEBSITE_ROOT.resolve() not in candidate.parents or not candidate.is_file():
			return self.send_bytes(b"Not found", "text/plain", 404)
		return self.send_bytes(candidate.read_bytes(), mimetypes.guess_type(candidate.name)[0] or "application/octet-stream")


class ApiHandler(BaseHandler):
	def cors_headers(self):
		return {"Access-Control-Allow-Origin": SITE_ORIGIN, "Vary": "Origin"}

	def do_OPTIONS(self):
		return self.send_bytes(b"Unexpected preflight", "text/plain", 418)

	def do_GET(self):
		path = urlparse(self.path).path
		if path == "/api/method/verity_ai.api.chat.get_widget_settings":
			payload = {"message": {
				"success": True,
				"assistant_name": "VerityAI",
				"title": "Verified Custom Widget",
				"greeting": "Verified custom greeting from another origin.",
				"primary_color": "#C026D3",
				"primary_dark_color": "#86198F",
				"header_background": "linear-gradient(135deg, #0F172A 0%, #C026D3 100%)",
				"show_branding": True,
				"max_message_chars": 4000,
			}}
			return self.send_bytes(json.dumps(payload).encode(), "application/json", headers=self.cors_headers())
		if path == "/widget.js":
			return self.send_bytes((ENGINE_ROOT / "js" / "widget.js").read_bytes(), "application/javascript", headers=self.cors_headers())
		if path == "/assets/verity_ai/css/widget.css":
			return self.send_bytes((ENGINE_ROOT / "css" / "widget.css").read_bytes(), "text/css", headers=self.cors_headers())
		return self.send_bytes(b"Not found", "text/plain", 404, self.cors_headers())


site = ThreadingHTTPServer(("127.0.0.1", 4183), SiteHandler)
api = ThreadingHTTPServer(("127.0.0.1", 4184), ApiHandler)
threading.Thread(target=api.serve_forever, daemon=True).start()
site.serve_forever()
