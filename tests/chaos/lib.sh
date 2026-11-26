#!/usr/bin/env bash
set -Eeuo pipefail

CHAOS_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
CHAOS_EVIDENCE_DIR="$CHAOS_ROOT/docs/evidencias/fase-10"
CHAOS_COMPOSE_FILES=(
  -f "$CHAOS_ROOT/infrastructure/compose/compose.distributed.yml"
  -f "$CHAOS_ROOT/infrastructure/compose/compose.central.yml"
  -f "$CHAOS_ROOT/tests/chaos/compose.d06-ports.yml"
)
CHAOS_PROJECT="${D06_COMPOSE_PROJECT:-d06-chaos}"
CHAOS_API_KEY="${API_KEY:-dev-api-key}"
CHAOS_CENTRAL_API_KEY="${CENTRAL_API_KEY:-dev-central-key}"
CHAOS_WH001_URL="${D06_WH001_URL:-http://127.0.0.1:18101}"
CHAOS_WH003_URL="${D06_WH003_URL:-http://127.0.0.1:18103}"
CHAOS_CENTRAL_URL="${D06_CENTRAL_URL:-http://127.0.0.1:18004}"
CHAOS_KEEP_STACK="${D06_KEEP_STACK:-false}"
CHAOS_EVIDENCE_FILE=""

chaos_compose() {
  docker compose -p "$CHAOS_PROJECT" "${CHAOS_COMPOSE_FILES[@]}" "$@"
}

chaos_log() {
  printf '%s\n' "$*" | tee -a "$CHAOS_EVIDENCE_FILE"
}

chaos_sql_wh() {
  local service="$1" sql="$2"
  chaos_compose exec -T "${service}_db" psql -U admin -d platform -At -v ON_ERROR_STOP=1 -c "$sql"
}

chaos_sql_central() {
  local sql="$1"
  chaos_compose exec -T central-db psql -U central -d central -At -v ON_ERROR_STOP=1 -c "$sql"
}

chaos_wait() {
  local label="$1" command="$2" timeout="${3:-60}" start now
  start="$(date +%s)"
  while true; do
    if eval "$command" >/dev/null 2>&1; then
      chaos_log "OK: $label"
      return 0
    fi
    now="$(date +%s)"
    if (( now - start >= timeout )); then
      chaos_log "ERROR: timeout esperando $label"
      return 1
    fi
    sleep 2
  done
}

chaos_prepare() {
  local case_id="$1" description="$2"
  mkdir -p "$CHAOS_EVIDENCE_DIR"
  CHAOS_EVIDENCE_FILE="$CHAOS_EVIDENCE_DIR/caso-${case_id}.txt"
  : > "$CHAOS_EVIDENCE_FILE"
  chaos_log "Caso $case_id: $description"
  chaos_log "Fecha UTC: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
  chaos_log "Rama: $(git -C "$CHAOS_ROOT" branch --show-current)"
  trap chaos_finish EXIT
  if ! docker image inspect d06-warehouse-api:local >/dev/null 2>&1 \
    || ! docker image inspect d06-central:local >/dev/null 2>&1; then
    chaos_compose build wh001_api central-api
  fi
  chaos_compose up -d
  chaos_wait "API WH-001 lista" "curl -fsS '$CHAOS_WH001_URL/health/ready'"
  chaos_wait "API central lista" "curl -fsS '$CHAOS_CENTRAL_URL/health/ready'"
}

chaos_finish() {
  local status="$?"
  trap - EXIT
  if [[ "$CHAOS_KEEP_STACK" != "true" ]]; then
    chaos_compose down || status=1
  fi
  if [[ -n "$CHAOS_EVIDENCE_FILE" ]]; then
    printf 'Exit code: %s\n' "$status" | tee -a "$CHAOS_EVIDENCE_FILE"
    printf 'Evidencia: %s\n' "$CHAOS_EVIDENCE_FILE"
  fi
  exit "$status"
}

chaos_post_receipt() {
  local reference="$1"
  curl -fsS -X POST "$CHAOS_WH001_URL/inventory/movements" \
    -H "X-API-Key: $CHAOS_API_KEY" -H 'Content-Type: application/json' \
    -d "{\"sku\":\"P-001\",\"type\":\"RECEIPT\",\"quantity\":1,\"reference\":\"$reference\"}"
}

chaos_outbox_max_id() {
  chaos_sql_wh wh001 'SELECT COALESCE(MAX(id), 0) FROM outbox'
}

chaos_require() {
  local condition="$1" message="$2"
  if ! eval "$condition"; then
    chaos_log "ERROR: $message"
    return 1
  fi
  chaos_log "OK: $message"
}
