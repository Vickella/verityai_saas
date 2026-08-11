from verityai_saas.services.permissions import require_platform_admin
from verityai_saas.services.admin_reauth import require_admin_reauthentication
from verityai_saas.www.verityai._common import portal_context


def get_context(context):
	require_platform_admin()
	require_admin_reauthentication()
	return portal_context(context, "integrations")
