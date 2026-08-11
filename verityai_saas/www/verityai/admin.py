from verityai_saas.services.permissions import require_operator
from verityai_saas.www.verityai._common import portal_context


def get_context(context):
	require_operator()
	portal_context(context, "admin")
	context.title = "VerityAI Operator Dashboard"
	return context
