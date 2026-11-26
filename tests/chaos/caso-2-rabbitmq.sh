#!/usr/bin/env bash
set -Eeuo pipefail
source "$(dirname "$0")/lib.sh"
chaos_prepare 2 "Outbox conserva publicaciones cuando RabbitMQ está caído"

before_id="$(chaos_outbox_max_id)"
reference="d06-caso-2-$(date -u +%Y%m%dT%H%M%SZ)-$$"
chaos_compose stop rabbitmq
chaos_log "Movimiento: $(chaos_post_receipt "$reference")"
chaos_wait "evento guardado en outbox pendiente" \
  "chaos_sql_wh wh001 \"SELECT COUNT(*) FROM outbox WHERE id > $before_id AND published_at IS NULL\" | grep -q '^[1-9]'"
chaos_log "Outbox pendiente: $(chaos_sql_wh wh001 "SELECT COUNT(*) FROM outbox WHERE id > $before_id AND published_at IS NULL")"
chaos_compose start rabbitmq
chaos_wait "RabbitMQ saludable" "chaos_compose exec -T rabbitmq rabbitmq-diagnostics -q ping" 90
chaos_wait "outbox publicado tras recuperar RabbitMQ" \
  "chaos_sql_wh wh001 \"SELECT COUNT(*) FROM outbox WHERE id > $before_id AND published_at IS NOT NULL\" | grep -q '^[1-9]'" 120
chaos_log "Outbox publicado: $(chaos_sql_wh wh001 "SELECT COUNT(*) FROM outbox WHERE id > $before_id AND published_at IS NOT NULL")"
