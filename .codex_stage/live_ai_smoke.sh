#!/usr/bin/env bash
set -euo pipefail
cd /home/frappe/frappe-bench
export PYTHONPATH=/mnt/c/Users/havano/Documents/vt/verityai_saas:/mnt/c/Users/havano/Documents/vt/verity_ai:${PYTHONPATH:-}
/home/frappe/.venv/frappe-bench/bin/bench --site farm.test execute verity_ai.engine.openai_handler.process_chat \
  --kwargs '{"tenant_name":"saas-isolation-tenant-1","session_id":"production-fix-business-context-20260820","message":"I am buying for TEST ABC Ltd, a manufacturing company with 3 users. I need all relevant modules including manufacturing because Odoo lacks detailed stock movements and financial budgets. Briefly tell me what else you need for a quotation. Do not treat the organisation operating this assistant and my company as the same business.","platform":"Web"}'
