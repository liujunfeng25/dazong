#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
COMPOSE="$ROOT/qa/docker-compose.qa.yml"
OUTPUT="$ROOT/qa-reports/2026-06-12/evidence/security/dependency-readiness.json"
TMP="$(mktemp -d)"

cleanup() {
  docker compose -f "$COMPOSE" start mysql-qa minio-qa >/dev/null 2>&1 || true
  rm -rf "$TMP"
}
trap cleanup EXIT

mkdir -p "$(dirname "$OUTPUT")"

TOKEN="$(
  curl -fsS -X POST http://127.0.0.1:18000/api/auth/login \
    -H 'Content-Type: application/json' \
    -d '{"username":"delivery001","password":"demo123"}' |
    jq -r '.token'
)"

probe() {
  local name="$1"
  local url="$2"
  shift 2
  local body="$TMP/$name.body"
  local meta="$TMP/$name.meta"
  curl -sS --max-time 5 -o "$body" -w '%{http_code} %{time_total}' "$@" "$url" >"$meta" || true
  local status elapsed
  read -r status elapsed <"$meta" || true
  jq -n \
    --arg status "${status:-curl_error}" \
    --arg elapsed "${elapsed:-5}" \
    --rawfile body "$body" \
    '{status:$status,elapsed_seconds:($elapsed|tonumber?),body_preview:($body[0:500])}'
}

probe baseline_health http://127.0.0.1:18000/api/system/healthz >"$TMP/baseline_health.json"
probe baseline_ready http://127.0.0.1:18000/api/system/readyz >"$TMP/baseline_ready.json"

docker compose -f "$COMPOSE" stop minio-qa >/dev/null
probe minio_down_health http://127.0.0.1:18000/api/system/healthz >"$TMP/minio_down_health.json"
probe minio_down_ready http://127.0.0.1:18000/api/system/readyz >"$TMP/minio_down_ready.json"
docker compose -f "$COMPOSE" start minio-qa >/dev/null

docker compose -f "$COMPOSE" stop mysql-qa >/dev/null
sleep 2
probe mysql_down_health http://127.0.0.1:18000/api/system/healthz >"$TMP/mysql_down_health.json"
probe mysql_down_ready http://127.0.0.1:18000/api/system/readyz >"$TMP/mysql_down_ready.json"
probe mysql_down_authenticated http://127.0.0.1:18000/api/auth/me \
  -H "Authorization: Bearer $TOKEN" >"$TMP/mysql_down_authenticated.json"
docker compose -f "$COMPOSE" start mysql-qa >/dev/null

for _ in $(seq 1 30); do
  if docker compose -f "$COMPOSE" exec -T mysql-qa \
    mysqladmin ping -h127.0.0.1 -uroot -pqa_root_password --silent >/dev/null 2>&1; then
    break
  fi
  sleep 1
done
probe recovered_ready http://127.0.0.1:18000/api/system/readyz >"$TMP/recovered_ready.json"

jq -n \
  --slurpfile baseline_health "$TMP/baseline_health.json" \
  --slurpfile baseline_ready "$TMP/baseline_ready.json" \
  --slurpfile minio_down_health "$TMP/minio_down_health.json" \
  --slurpfile minio_down_ready "$TMP/minio_down_ready.json" \
  --slurpfile mysql_down_health "$TMP/mysql_down_health.json" \
  --slurpfile mysql_down_ready "$TMP/mysql_down_ready.json" \
  --slurpfile mysql_down_authenticated "$TMP/mysql_down_authenticated.json" \
  --slurpfile recovered_ready "$TMP/recovered_ready.json" \
  '{
    baseline:{health:$baseline_health[0],ready:$baseline_ready[0]},
    minio_down:{health:$minio_down_health[0],ready:$minio_down_ready[0]},
    mysql_down:{
      health:$mysql_down_health[0],
      ready:$mysql_down_ready[0],
      authenticated_request:$mysql_down_authenticated[0]
    },
    recovered:{ready:$recovered_ready[0]},
    token_recorded:false
  }' >"$OUTPUT"

cat "$OUTPUT"
