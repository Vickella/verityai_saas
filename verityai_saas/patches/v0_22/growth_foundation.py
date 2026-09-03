from verityai_saas.services.growth import seed_default_channels
from verityai_saas.setup_doctypes import ensure_growth_doctypes, ensure_platform_settings


def execute():
	ensure_platform_settings()
	ensure_growth_doctypes()
	seed_default_channels()
