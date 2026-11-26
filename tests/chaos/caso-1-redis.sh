#!/usr/bin/env bash
set -Eeuo pipefail
source "$(dirname "$0")/lib.sh"
chaos_prepare 1 "Redis detenido conserva lectura desde PostgreSQL"

chaos_compose stop wh001_redis
headers="$(mktemp)" body="$(mktemp)"
status="$(curl -sS -D "$headers" -o "$body" -w '%{http_code}' \
  -H "X-API-Key: $CHAOS_API_KEY" "$CHAOS_WH001_URL/inventory/P-001")"
cache_header="$(awk 'tolower($1)=="x-cache:" {gsub("\r", "", $2); print toupper($2)}' "$headers" | tail -n 1)"
chaos_log "HTTP: $status; X-Cache: $cache_header"
cat "$body" | tee -a "$CHAOS_EVIDENCE_FILE"
chaos_require '[[ "$status" == 200 && "$cache_header" == BYPASS ]]' \
  "la API devuelve 200 y X-Cache: BYPASS con Redis detenido"
rm -f "$headers" "$body"
chaos_compose start wh001_redis
chaos_wait "Redis recuperado" "chaos_compose exec -T wh001_redis redis-cli ping | grep -q PONG"
