from verityai_saas.services.permissions import require_operator


def get_context(context):
	require_operator()
	context.no_cache = 1
	context.title = "VerityAI Operator Dashboard"
	return context