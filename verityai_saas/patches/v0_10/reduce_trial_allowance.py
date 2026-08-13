from verityai_saas.services.billing import apply_trial_allowance_limit
from verityai_saas.setup_doctypes import ensure_default_plan


def execute():
	ensure_default_plan()
	apply_trial_allowance_limit(10_000)
