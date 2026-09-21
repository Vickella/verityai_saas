from verity_ai.engine.openai_handler import consolidate_all_whatsapp_sessions
from verityai_saas.setup_doctypes import ensure_doctypes


def execute():
	ensure_doctypes()
	consolidate_all_whatsapp_sessions()
