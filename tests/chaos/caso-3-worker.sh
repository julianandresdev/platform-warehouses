#!/usr/bin/env bash
set -Eeuo pipefail
source "$(dirname "$0")/lib.sh"
chaos_prepare 3 "La proyección espera mensajes mientras el worker está detenido"

before_id="$(chaos_outbox_max_id)"
chaos_compose stop central-worker
reference="d06-caso-3-$(date -u +%Y%m%dT%H%M%SZ)-$$"
chaos_log "Movimiento: $(chaos_post_receipt "$reference")"
chaos_wait "evento publicado en outbox" \
  "chaos_sql_wh wh001 \"SELECT COUNT(*) FROM outbox WHERE id > $before_id AND published_at IS NOT NULL\" | grep -q '^[1-9]'"
event_version="$(chaos_sql_wh wh001 "SELECT payload #>> '{payload,version}' FROM outbox WHERE id > $before_id ORDER BY id DESC LIMIT 1")"
ready="$(chaos_compose exec -T rabbitmq rabbitmqctl list_queues --quiet name messages_ready | awk '$1=="central.projection" {print $2}')"
chaos_log "Versión esperada: $event_version; mensajes pendientes en central.projection: ${ready:-0}"
chaos_require '[[ "${ready:-0}" =~ ^[1-9][0-9]*$ ]]' "el evento espera en la cola de proyección"
chaos_compose start central-worker
projection_applied() {
  local version
  version="$(chaos_sql_central "SELECT COALESCE(MAX(version),0) FROM global_inventory WHERE sku='P-001' AND warehouse_id='WH-001'")"
  [[ "$version" =~ ^[0-9]+$ ]] && (( version >= event_version ))
}
chaos_wait "worker central recupera el mensaje" projection_applied 90
chaos_log "Versión proyectada: $(chaos_sql_central "SELECT version FROM global_inventory WHERE sku='P-001' AND warehouse_id='WH-001'")"
