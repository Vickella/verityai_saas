#!/usr/bin/env bash
set -euo pipefail
bench=/home/frappe/frappe-bench
app="$bench/apps/verityai_saas"
win=/mnt/c/Users/havano/Documents/vt/verityai_saas
backup="/tmp/verityai_saas-pre-import-$(date +%Y%m%d%H%M%S)"
files=(
  pyproject.toml
  verityai_saas/setup_doctypes.py
  verityai_saas/services/paynow.py
  verityai_saas/services/commerce.py
  verityai_saas/api/admin.py
  verityai_saas/api/commerce.py
  verityai_saas/public/js/admin.js
  verityai_saas/public/js/portal.js
  verityai_saas/public/css/portal.css
  verityai_saas/www/verityai/admin.html
  verityai_saas/tests/test_commerce.py
  verityai_saas/tests/test_paynow.py
  verityai_saas/tests/test_integrations.py
)
mkdir -p "$backup"
for file in "${files[@]}"; do
  mkdir -p "$backup/$(dirname "$file")"
  cp "$app/$file" "$backup/$file"
  cp "$win/$file" "$app/$file"
done
echo "Backup: $backup"
