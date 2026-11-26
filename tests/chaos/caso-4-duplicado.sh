#!/usr/bin/env bash
set -Eeuo pipefail
source "$(dirname "$0")/lib.sh"
chaos_prepare 4 "Un event_id repetido produce un solo efecto de proyección y auditoría"

event_id="$(chaos_compose exec -T wh001_api python - <<'PY'
import uuid
from common.events import EventEnvelope
from common.rabbit import publish

event = EventEnvelope(
    event_id=uuid.uuid4(), event_type="WAREHOUSE_HEARTBEAT", event_version=1,
    occurred_at=__import__("datetime").datetime.now(__import__("datetime").timezone.utc),
    correlation_id="d06-chaos-duplicate", source="warehouse-WH-001",
    payload={"warehouse_id": "WH-001"},
)
publish(event, "warehouse.events", "warehouse.WH-001.heartbeat")
publish(event, "warehouse.events", "warehouse.WH-001.heartbeat")
print(event.event_id)
PY
)"
chaos_log "Evento publicado dos veces: $event_id"
single_audit_record() {
  [[ "$(chaos_sql_central "SELECT COUNT(*) FROM audit_events WHERE event_id='$event_id'")" == 1 ]]
}
chaos_wait "un único registro de auditoría" single_audit_record 60
processed="$(chaos_sql_central "SELECT COUNT(*) FROM processed_messages WHERE message_id='$event_id' AND consumer='central.projection'")"
audited="$(chaos_sql_central "SELECT COUNT(*) FROM audit_events WHERE event_id='$event_id'")"
chaos_log "Efectos únicos: proyección=$processed, auditoría=$audited"
chaos_require '[[ "$processed" == 1 && "$audited" == 1 ]]' \
  "la proyección y auditoría deduplican el mismo event_id"
