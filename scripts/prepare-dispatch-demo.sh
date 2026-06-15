#!/usr/bin/env bash
# 一键准备智能排线/司机端演示数据。
# 用法：
#   bash scripts/prepare-dispatch-demo.sh https://你的-ngrok/api 2026-05-21
# 默认使用 monitor001 / demo123 登录；也可提前设置 MONITOR_TOKEN。
set -euo pipefail

API_BASE="${1:-http://127.0.0.1:8000/api}"
PLANNING_DATE="${2:-}"
API_BASE="${API_BASE%/}"

if [[ -z "${MONITOR_TOKEN:-}" ]]; then
  LOGIN_JSON="$(curl -fsS -X POST "$API_BASE/auth/login" \
    -H 'Content-Type: application/json' \
    -d '{"username":"monitor001","password":"demo123"}')"
  MONITOR_TOKEN="$(python3 -c 'import json,sys; print(json.load(sys.stdin)["token"])' <<< "$LOGIN_JSON")"
fi

BODY="$(python3 - "$PLANNING_DATE" <<'PY'
import json
import sys

planning_date = (sys.argv[1] or "").strip()
body = {
    "delivery_username": "delivery001",
    "target_order_count": 6,
    "create_if_missing": True,
    "mark_shipped": True,
    "mark_sorted": True,
}
if planning_date:
    body["planning_date"] = planning_date
print(json.dumps(body, ensure_ascii=False))
PY
)"

curl -fsS -X POST "$API_BASE/demo/dispatch/prepare" \
  -H "Authorization: Bearer $MONITOR_TOKEN" \
  -H 'Content-Type: application/json' \
  -d "$BODY"
echo
