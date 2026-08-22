import frappe


frappe.init(site="farm.test", sites_path="/home/frappe/frappe-bench/sites")
try:
	from verityai_saas.services.ingestion import crawl_url

	content, pages, size = crawl_url("https://veritycore.co.zw", max_pages=5)
	print({
		"pages": pages,
		"bytes": size,
		"characters": len(content),
		"contains_veritycore": "veritycore" in content.lower(),
		"contains_services": "services" in content.lower(),
	})
finally:
	frappe.destroy()
