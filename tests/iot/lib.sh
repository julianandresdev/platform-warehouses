#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"
COMPOSE=(docker compose -p d07-iot -f docker-compose.yaml -f tests/iot/compose.d07-ports.yml --profile iot)

d07_up() {
  mkdir -p docs/evidencias/fase-12
  "${COMPOSE[@]}" down --volumes --remove-orphans >/dev/null 2>&1 || true
  "${COMPOSE[@]}" build iot-ingestion iot-storage-worker iot-alert-worker iot-simulator
  "${COMPOSE[@]}" up -d rabbitmq rabbitmq-topology mosquitto iot-db iot-ingestion iot-storage-worker iot-alert-worker
  for _ in $(seq 1 90); do
    if curl -fsS http://127.0.0.1:29103/metrics >/dev/null 2>&1 && curl -fsS http://127.0.0.1:29104/metrics >/dev/null 2>&1 && curl -fsS http://127.0.0.1:29105/metrics >/dev/null 2>&1; then return 0; fi
    sleep 2
  done
  "${COMPOSE[@]}" ps
  return 1
}

d07_reset() {
  "${COMPOSE[@]}" exec -T iot-db psql -U iot -d iot -c "TRUNCATE sensor_alerts, sensor_alert_state, sensor_processed_messages, sensor_readings, sensor_state RESTART IDENTITY CASCADE; UPDATE sensor_ingestion_stats SET received=0, stored_unique=0, duplicates_discarded=0, out_of_order=0 WHERE singleton=TRUE;" >/dev/null
  "${COMPOSE[@]}" run --rm --no-deps --entrypoint sh iot-simulator -c 'rm -f /var/lib/iot-spool/spool.sqlite3*'
}

d07_run_simulator() {
  "${COMPOSE[@]}" run --rm --no-deps \
    -e SENSOR_COUNT="${SENSOR_COUNT:-10}" \
    -e PUBLISH_INTERVAL_SECONDS="${PUBLISH_INTERVAL_SECONDS:-0.2}" \
    -e SIM_DURATION_SECONDS="${SIM_DURATION_SECONDS:-8}" \
    -e DUP_RATE="${DUP_RATE:-0.25}" \
    -e REORDER_RATE="${REORDER_RATE:-0.2}" \
    -e SIMULATED_OUTAGE_START_SECONDS="${SIMULATED_OUTAGE_START_SECONDS:-2}" \
    -e SIMULATED_OUTAGE_DURATION_SECONDS="${SIMULATED_OUTAGE_DURATION_SECONDS:-2}" \
    -e SIMULATOR_SUMMARY_PATH="${SIMULATOR_SUMMARY_PATH:-/evidence/simulacion-smoke.json}" iot-simulator
}

d07_verify() {
  local summary="${1:-docs/evidencias/fase-12/simulacion-smoke.json}"
  for _ in $(seq 1 30); do
    [[ -s "$summary" ]] && break
    sleep 1
  done
  local expected
  expected="$(python -c 'import json,sys; print(json.load(open(sys.argv[1], encoding="utf-8"))["mqtt_publish_acknowledged"])' "$summary")"
  local gateway_published=0
  for _ in $(seq 1 180); do
    local stats
    gateway_published="$(curl -fsS http://127.0.0.1:29103/metrics | awk '$1 == "iot_rabbit_readings_published_total" {print $2; exit}' | cut -d. -f1)"
    gateway_published="${gateway_published:-0}"
    stats="$("${COMPOSE[@]}" exec -T iot-db psql -U iot -d iot -Atc "SELECT received || ',' || stored_unique || ',' || duplicates_discarded || ',' || out_of_order || ',' || COALESCE((SELECT SUM(GREATEST(s.last_sequence-COALESCE(r.reading_count,0),0)) FROM sensor_state s LEFT JOIN (SELECT sensor_id,COUNT(*) reading_count FROM sensor_readings GROUP BY sensor_id) r USING(sensor_id)),0) FROM sensor_ingestion_stats WHERE singleton=TRUE")"
    local received unique duplicates out_of_order gaps
    IFS=, read -r received unique duplicates out_of_order gaps <<< "$stats"
    if [[ "$gateway_published" -eq "$expected" && "$received" -eq "$expected" && "$gaps" -eq 0 ]]; then break; fi
    sleep 1
  done
  python - "$summary" "$expected" "$gateway_published" "$received" "$unique" "$duplicates" "$out_of_order" "$gaps" <<'PY'
import json, sys
from pathlib import Path
summary = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
expected, gateway_published, received, unique, duplicates, out_of_order, gaps = map(int, sys.argv[2:])
assert summary["buffer_remaining"] == 0, summary
assert gateway_published == expected, (expected, gateway_published)
assert expected == received, (expected, received)
assert summary["mqtt_publish_acknowledged"] == unique + duplicates, (summary, unique, duplicates)
assert received == unique + duplicates, (received, unique, duplicates)
assert out_of_order > 0, "No se ejercitó la ruta de lecturas fuera de orden"
assert gaps == 0, f"Quedaron {gaps} huecos de secuencia tras recibir toda la corrida"
assert summary["buffered_at_outage_start"] > 0, "El corte no dejó lecturas en el spool"
print(json.dumps({"simulator": summary, "received": received, "stored_unique": unique, "duplicates_discarded": duplicates, "out_of_order": out_of_order, "gaps": gaps}, indent=2))
PY
}

d07_down() { "${COMPOSE[@]}" down --volumes --remove-orphans; }
