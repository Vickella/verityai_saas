import json
import time

import frappe
import requests


ENDPOINT = "https://www.googleapis.com/pagespeedonline/v5/runPagespeed"
MAX_PROVIDER_BYTES = 4 * 1024 * 1024
CATEGORIES = ("performance", "accessibility", "seo")


def _finding(category, code, score):
	status = "Pass" if score >= 90 else ("Warning" if score >= 50 else "Fail")
	return {
		"category": category,
		"check_code": code,
		"status": status,
		"source": "PageSpeed",
		"summary": f"PageSpeed {category.lower()} score: {score}.",
		"measured": {"score": score, "strategy": "mobile"},
		"recommendation": "Review the measured PageSpeed diagnostics for this category." if status != "Pass" else "",
	}


def normalize_response(payload):
	categories = ((payload or {}).get("lighthouseResult") or {}).get("categories") or {}
	mapping = {
		"performance": "Performance",
		"accessibility": "Accessibility",
		"seo": "Technical SEO",
	}
	findings = []
	for provider_key, category in mapping.items():
		value = (categories.get(provider_key) or {}).get("score")
		if isinstance(value, (int, float)):
			findings.append(_finding(category, f"pagespeed_{provider_key.replace('-', '_')}", round(value * 100)))
	return findings


def run_pagespeed(url, session=None):
	api_key = str(frappe.conf.get("verityai_pagespeed_api_key") or "").strip()
	if not api_key:
		return [], 0, 0
	client = session or requests.Session()
	client.trust_env = False
	params = [("url", url), ("strategy", "mobile"), ("key", api_key)]
	params.extend(("category", category) for category in CATEGORIES)
	started = time.monotonic()
	response = client.get(ENDPOINT, params=params, timeout=(5, 45), stream=True)
	try:
		response.raise_for_status()
		chunks, total = [], 0
		for chunk in response.iter_content(65536):
			total += len(chunk)
			if total > MAX_PROVIDER_BYTES:
				frappe.throw("PageSpeed response exceeded the provider size limit.", frappe.ValidationError)
			chunks.append(chunk)
	finally:
		response.close()
	payload = json.loads(b"".join(chunks).decode("utf-8"))
	duration = max(round((time.monotonic() - started) * 1000), 1)
	cost = float(frappe.conf.get("verityai_pagespeed_cost_usd") or 0)
	return normalize_response(payload), duration, cost
