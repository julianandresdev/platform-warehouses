#!/usr/bin/env bash
set -Eeuo pipefail
source "$(dirname "$0")/lib.sh"
chaos_prepare 5 "La central sigue disponible y marca WH-003 obsoleta cuando su API y relay caen"

chaos_wait "WH-003 con heartbeat conocido" \
  "chaos_sql_central \"SELECT COUNT(*) FROM warehouse_status WHERE warehouse_id='WH-003' AND last_seen_at IS NOT NULL\" | grep -q '^[1-9]'" 120
chaos_compose stop wh003_api wh003_worker
chaos_wait "WH-003 marcada stale" \
  "curl -fsS -H 'X-API-Key: $CHAOS_CENTRAL_API_KEY' '$CHAOS_CENTRAL_URL/global/warehouses' | grep -E 'WH-003.{0,200}true|true.{0,200}WH-003'" 150
chaos_log "Estado central: $(curl -fsS -H "X-API-Key: $CHAOS_CENTRAL_API_KEY" "$CHAOS_CENTRAL_URL/global/warehouses")"
chaos_log "Health central: $(curl -fsS "$CHAOS_CENTRAL_URL/health")"
chaos_compose start wh003_api wh003_worker
chaos_wait "WH-003 API recuperada" "curl -fsS '$CHAOS_WH003_URL/health/ready'" 120
