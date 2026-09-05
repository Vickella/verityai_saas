from html.parser import HTMLParser


CATEGORY_WEIGHTS = {
	"Performance": 1.0,
	"Technical SEO": 1.0,
	"Metadata": 1.0,
	"Mobile Readiness": 1.0,
	"Accessibility": 1.0,
	"Security": 1.0,
	"Content Quality": 1.0,
	"Conversion": 1.0,
	"AI Readiness": 1.0,
	"Structured Data": 1.0,
	"Page Architecture": 1.0,
}
STATUS_SCORE = {"Pass": 100, "Warning": 50, "Fail": 0}


class AuditHTMLParser(HTMLParser):
	def __init__(self):
		super().__init__()
		self.title_parts = []
		self.in_title = False
		self.meta = []
		self.headings = {"h1": 0, "h2": 0}
		self.images = []
		self.links = []
		self.forms = 0
		self.buttons = 0
		self.json_ld = 0
		self.html_lang = ""
		self.canonical_url = ""
		self.visible_text = []
		self.ignored_depth = 0

	def handle_starttag(self, tag, attrs):
		attributes = {str(key).lower(): value for key, value in attrs}
		tag = tag.lower()
		if tag == "html":
			self.html_lang = str(attributes.get("lang") or "").strip()
		elif tag == "title":
			self.in_title = True
		elif tag == "meta":
			self.meta.append(attributes)
		elif tag in {"script", "style", "noscript", "svg"}:
			self.ignored_depth += 1
		elif tag in self.headings:
			self.headings[tag] += 1
		elif tag == "img":
			self.images.append(attributes)
		elif tag == "a":
			self.links.append(attributes)
		elif tag == "link" and "canonical" in str(attributes.get("rel") or "").lower().split():
			self.canonical_url = str(attributes.get("href") or "").strip()
		elif tag == "form":
			self.forms += 1
		elif tag == "button":
			self.buttons += 1
		elif tag == "script" and str(attributes.get("type") or "").lower() == "application/ld+json":
			self.json_ld += 1

	def handle_endtag(self, tag):
		if tag.lower() == "title":
			self.in_title = False
		elif tag.lower() in {"script", "style", "noscript", "svg"} and self.ignored_depth:
			self.ignored_depth -= 1

	def handle_data(self, data):
		if self.in_title and data.strip():
			self.title_parts.append(data.strip())
		if not self.ignored_depth and data.strip():
			self.visible_text.append(data.strip())


def _finding(category, code, status, summary, measured, recommendation):
	return {
		"category": category,
		"check_code": code,
		"status": status,
		"source": "Deterministic",
		"summary": summary,
		"measured": measured,
		"recommendation": recommendation if status != "Pass" else "",
	}


def deterministic_checks(fetch_result):
	encoding = "utf-8"
	content_type = fetch_result.headers.get("content-type", "")
	if "charset=" in content_type.lower():
		encoding = content_type.lower().split("charset=", 1)[1].split(";", 1)[0].strip() or "utf-8"
	html = fetch_result.body.decode(encoding, errors="replace")
	parser = AuditHTMLParser()
	parser.feed(html)
	title = " ".join(parser.title_parts).strip()
	description = next(
		(
			str(item.get("content") or "").strip()
			for item in parser.meta
			if str(item.get("name") or "").lower() == "description"
		),
		"",
	)
	viewport = any(str(item.get("name") or "").lower() == "viewport" for item in parser.meta)
	missing_alt = sum(not str(image.get("alt") or "").strip() for image in parser.images)
	word_count = len(" ".join(parser.visible_text).split())
	security_headers = {
		name: bool(fetch_result.headers.get(name))
		for name in (
			"content-security-policy",
			"strict-transport-security",
			"x-content-type-options",
			"referrer-policy",
		)
	}
	secure_count = sum(security_headers.values())
	findings = [
		_finding(
			"Metadata", "page_title",
			"Pass" if 10 <= len(title) <= 65 else ("Warning" if title else "Fail"),
			f"Page title length: {len(title)} characters.", {"length": len(title)},
			"Add a unique, descriptive page title of roughly 10-65 characters.",
		),
		_finding(
			"Metadata", "meta_description",
			"Pass" if 50 <= len(description) <= 170 else ("Warning" if description else "Fail"),
			f"Meta description length: {len(description)} characters.", {"length": len(description)},
			"Add a clear page description that explains the offer and value.",
		),
		_finding(
			"Technical SEO", "canonical_link", "Pass" if parser.canonical_url else "Warning",
			"A canonical URL was declared." if parser.canonical_url else "No canonical URL was declared.",
			{"present": bool(parser.canonical_url)}, "Declare the preferred canonical URL for this page.",
		),
		_finding(
			"Mobile Readiness", "viewport", "Pass" if viewport else "Fail",
			"A viewport meta tag was found." if viewport else "No viewport meta tag was found.",
			{"present": viewport}, "Add a responsive viewport meta tag for mobile browsers.",
		),
		_finding(
			"Accessibility", "image_alt", "Pass" if not missing_alt else "Warning",
			f"{missing_alt} of {len(parser.images)} images have no non-empty alt text.",
			{"images": len(parser.images), "missing_alt": missing_alt},
			"Add meaningful alt text to informative images; use empty alt text only for decorative images.",
		),
		_finding(
			"Accessibility", "document_language", "Pass" if parser.html_lang else "Warning",
			f"Document language: {parser.html_lang or 'not declared'}.", {"language": parser.html_lang},
			"Declare the page language on the HTML element.",
		),
		_finding(
			"Security", "security_headers",
			"Pass" if secure_count == len(security_headers) else ("Warning" if secure_count >= 2 else "Fail"),
			f"{secure_count} of {len(security_headers)} selected security headers were present.",
			security_headers, "Configure CSP, HSTS, X-Content-Type-Options and Referrer-Policy where appropriate.",
		),
		_finding(
			"Content Quality", "content_depth",
			"Pass" if word_count >= 250 else ("Warning" if word_count >= 80 else "Fail"),
			f"Approximately {word_count} visible words were measured on the page.",
			{"visible_word_count": word_count},
			"Add useful, specific content that answers visitors' main questions without padding.",
		),
		_finding(
			"Page Architecture", "single_h1",
			"Pass" if parser.headings["h1"] == 1 else ("Warning" if parser.headings["h1"] > 1 else "Fail"),
			f"H1 headings found: {parser.headings['h1']}.", parser.headings,
			"Use one clear primary H1 heading and organise supporting sections with lower-level headings.",
		),
		_finding(
			"Conversion", "conversion_controls", "Pass" if parser.forms or parser.buttons else "Warning",
			f"Forms: {parser.forms}; buttons: {parser.buttons}.",
			{"forms": parser.forms, "buttons": parser.buttons},
			"Add a clear, relevant next action such as a contact, booking or enquiry control.",
		),
		_finding(
			"Structured Data", "json_ld", "Pass" if parser.json_ld else "Warning",
			f"JSON-LD blocks found: {parser.json_ld}.", {"json_ld_blocks": parser.json_ld},
			"Consider valid JSON-LD that accurately describes the business and page content.",
		),
		_finding(
			"AI Readiness", "descriptive_structure",
			"Pass" if title and parser.headings["h1"] == 1 and description else "Warning",
			"Title, description and heading structure were checked.",
			{"title": bool(title), "description": bool(description), "h1_count": parser.headings["h1"]},
			"Use explicit titles, descriptions and headings so people and automated systems can understand the page.",
		),
	]
	return findings


def score_findings(findings):
	category_scores = {}
	for category in CATEGORY_WEIGHTS:
		values = [
			STATUS_SCORE[row["status"]]
			for row in findings
			if row["category"] == category and row["status"] in STATUS_SCORE
		]
		if values:
			category_scores[category] = round(sum(values) / len(values))
	weighted = sum(category_scores[name] * CATEGORY_WEIGHTS[name] for name in category_scores)
	weight = sum(CATEGORY_WEIGHTS[name] for name in category_scores)
	return (round(weighted / weight) if weight else 0), category_scores
