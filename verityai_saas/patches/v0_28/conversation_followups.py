def execute():
	from verityai_saas.setup_doctypes import ensure_doctypes
	from verityai_saas.services.campaigns import sync_all_campaign_contexts

	ensure_doctypes()
	# Apply the tighter relevance and sales-conversion guidance to campaigns
	# that were already active before this release.
	sync_all_campaign_contexts()
