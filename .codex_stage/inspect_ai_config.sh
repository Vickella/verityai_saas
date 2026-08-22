#!/usr/bin/env bash
set -euo pipefail
cd /home/frappe/frappe-bench
/home/frappe/.venv/frappe-bench/bin/bench --site farm.test execute frappe.get_all \
  --kwargs '{"doctype":"AI Configuration","fields":["name","tenant","ai_provider","model_name"]}'
