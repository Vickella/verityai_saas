from verityai_saas.services.permissions import require_operator
from verityai_saas.services.admin_reauth import is_admin_reauthenticated
from verityai_saas.www.verityai._common import portal_context


def get_context(context):
	require_operator()
	portal_context(context, "admin")
	context.title = "VerityAI Operator Dashboard"
	context.admin_unlocked = is_admin_reauthenticated()
	return context
