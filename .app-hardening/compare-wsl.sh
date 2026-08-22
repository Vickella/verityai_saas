#!/usr/bin/env bash
set -euo pipefail
cd /home/frappe/frappe-bench/apps/verityai_saas
win=/mnt/c/Users/havano/Documents/vt/verityai_saas
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
for file in "${files[@]}"; do
  if cmp -s "$file" "$win/$file"; then
    echo "SAME $file"
  else
    echo "DIFF $file"
  fi
done
