import json
import mimetypes
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

WEBSITE_ROOT = Path(r"C:\Users\havano\Documents\vt\saas_ai_website")
ENGINE_ROOT = Path(r"C:\Users\havano\Documents\vt\verity_ai\verity_ai\public")
ORIGIN = "http://127.0.0.1:4174"


class Handler(BaseHTTPRequestHandler):
	def send_bytes(self, body, content_type, status=200):
		self.send_response(status)
		self.send_header("Content-Type", content_type)
		self.send_header("Cache-Control", "no-store")
		self.send_header("Access-Control-Allow-Origin", "*")
		self.end_headers()
		self.wfile.write(body)

	def do_GET(self):
		path = urlparse(self.path).path
		if path == "/api/method/verity_ai.api.chat.get_widget_settings":
			payload = {"message": {
				"success": True,
				"assistant_name": "VerityAI",
				"title": "VerityCore Sales Guide",
				"greeting": "Welcome to VerityCore. How can I help today?",
				"primary_color": "#C026D3",
				"primary_dark_color": "#86198F",
				"header_background": "linear-gradient(135deg, #0F172A 0%, #C026D3 100%)",
				"show_branding": True,
				"max_message_chars": 4000,
			}}
			return self.send_bytes(json.dumps(payload).encode(), "application/json")
		if path == "/widget.js":
			return self.send_bytes((ENGINE_ROOT / "js" / "widget.js").read_bytes(), "application/javascript")
		if path == "/assets/verity_ai/css/widget.css":
			return self.send_bytes((ENGINE_ROOT / "css" / "widget.css").read_bytes(), "text/css")
		if path in ("/", "/index.html"):
			html = (WEBSITE_ROOT / "index.html").read_text(encoding="utf-8")
			html = html.replace(
				'<script src="https://saasai.veritypack.cloud/assets/verity_ai/js/widget.js" data-tenant-id="veritycore"></script>',
				f'<script src="{ORIGIN}/widget.js" data-tenant-id="veritycore"></script>'
				'<script>setTimeout(()=>document.getElementById("verity-fab")?.click(),700)</script>',
			)
			return self.send_bytes(html.encode(), "text/html; charset=utf-8")
		relative = path.lstrip("/")
		candidate = (WEBSITE_ROOT / relative).resolve()
		if WEBSITE_ROOT.resolve() not in candidate.parents or not candidate.is_file():
			return self.send_bytes(b"Not found", "text/plain", 404)
		content_type = mimetypes.guess_type(candidate.name)[0] or "application/octet-stream"
		return self.send_bytes(candidate.read_bytes(), content_type)

	def log_message(self, *_args):
		return


ThreadingHTTPServer(("127.0.0.1", 4174), Handler).serve_forever()
