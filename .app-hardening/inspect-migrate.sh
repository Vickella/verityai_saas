#!/usr/bin/env bash
ps -eo pid,etime,stat,cmd | grep 'bench --site farm.test migrate' | grep -v grep || true
tail -40 /home/frappe/frappe-bench/logs/bench.log 2>/dev/null || true
