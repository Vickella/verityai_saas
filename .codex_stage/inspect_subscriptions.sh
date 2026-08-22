#!/usr/bin/env bash
set -euo pipefail
cd /home/frappe/frappe-bench
/home/frappe/.venv/frappe-bench/bin/bench --site farm.test execute frappe.get_all \
  --kwargs '{"doctype":"VerityAI Subscription","fields":["workspace","status","plan","trial_end","current_period_end"],"filters":{"status":["in",["Active","Trialing"]]},"limit_page_length":50}'
