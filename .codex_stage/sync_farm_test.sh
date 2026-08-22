#!/usr/bin/env bash
set -euo pipefail
SAAS_SRC=/mnt/c/Users/havano/Documents/vt/verityai_saas/verityai_saas
SAAS_DST=/home/frappe/frappe-bench/apps/verityai_saas/verityai_saas
ENGINE_SRC=/mnt/c/Users/havano/Documents/vt/verity_ai/verity_ai
ENGINE_DST=/home/frappe/frappe-bench/apps/verity_ai/verity_ai
for file in api/health.py api/knowledge.py api/quotes.py public/css/portal.css public/js/portal.js services/commerce.py services/health.py services/ingestion.py; do
  cp "$SAAS_SRC/$file" "$SAAS_DST/$file"
done
for file in engine/openai_handler.py engine/tools.py; do
  cp "$ENGINE_SRC/$file" "$ENGINE_DST/$file"
done
cd /home/frappe/frappe-bench
/home/frappe/.venv/frappe-bench/bin/bench build --app verityai_saas
/home/frappe/.venv/frappe-bench/bin/bench --site farm.test clear-cache
