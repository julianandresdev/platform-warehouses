#!/usr/bin/env bash
# Pruebas de humo de la plataforma desplegada (S-09). Sale con código 1 si algo falla.
# Uso: API_KEY=... CENTRAL_API_KEY=... scripts/smoke.sh <ip-o-host>
#   Con localhost sirve también para el Compose local: PORT_WH2=8080 (WH-002 va por nginx).
set -uo pipefail

HOST=${1:?uso: scripts/smoke.sh <ip-o-host>}
API_KEY=${API_KEY:-dev-api-key}
CENTRAL_API_KEY=${CENTRAL_API_KEY:-dev-central-key}
fallos=0

ok()    { printf 'PASS  %s\n' "$1"; }
falla() { printf 'FAIL  %s\n' "$1"; fallos=$((fallos + 1)); }

http() { # <método> <url> [cabeceras y cuerpo para curl...]
  local metodo=$1 url=$2; shift 2
  curl -s -m 10 -o /tmp/smoke.body -w '%{http_code}' -X "$metodo" "$url" "$@"
}

PORT_WH2=${PORT_WH2:-8102}   # local: WH-002 se publica por nginx en el 8080
for par in WH-001:8101 WH-002:$PORT_WH2 WH-003:8103; do
  wh=${par%%:*}; puerto=${par#*:}
  [ "$(http GET "http://$HOST:$puerto/health")" = 200 ] && ok "$wh /health" || falla "$wh /health"
  [ "$(http GET "http://$HOST:$puerto/health/ready")" = 200 ] && ok "$wh /health/ready (base de datos)" || falla "$wh /health/ready"
  [ "$(http GET "http://$HOST:$puerto/inventory/P-001" -H "X-API-Key: $API_KEY")" = 200 ] \
    && ok "$wh GET /inventory/P-001" || falla "$wh GET /inventory/P-001"
done

[ "$(http GET "http://$HOST:8004/health/ready")" = 200 ] && ok "central /health/ready" || falla "central /health/ready"

# Transferencia completa por la Saga: 1 unidad de P-001 de WH-001 a WH-002.
corr="COR-SMOKE-$(date +%s)"
codigo=$(http POST "http://$HOST:8004/transfers" -H "X-API-Key: $CENTRAL_API_KEY" -H "Idempotency-Key: smoke-$(date +%s)" \
  -H "X-Correlation-ID: $corr" -H 'Content-Type: application/json' \
  -d '{"source_warehouse_id":"WH-001","destination_warehouse_id":"WH-002","sku":"P-001","quantity":1}')
if [ "$codigo" = 202 ]; then
  id=$(python3 -c "import json;print(json.load(open('/tmp/smoke.body'))['transfer_id'])")
  estado=""
  for _ in $(seq 1 30); do
    http GET "http://$HOST:8004/transfers/$id" -H "X-API-Key: $CENTRAL_API_KEY" >/dev/null
    estado=$(python3 -c "import json;print(json.load(open('/tmp/smoke.body'))['status'])")
    [ "$estado" = COMPLETED ] && break
    sleep 1
  done
  [ "$estado" = COMPLETED ] && ok "transferencia $id COMPLETED ($corr)" || falla "transferencia $id quedó en $estado"
else
  falla "POST /transfers respondió $codigo"
fi

[ "$(http GET "http://$HOST:8004/global/inventory" -H "X-API-Key: $CENTRAL_API_KEY")" = 200 ] \
  && ok "central GET /global/inventory (vista global)" || falla "central GET /global/inventory"

echo
[ "$fallos" -eq 0 ] && echo "Todo en orden." || echo "$fallos prueba(s) fallaron."
exit $((fallos > 0))
