#!/usr/bin/env bash
# Guion de la demo (J-10): cada paso de docs/demo.md es un subcomando de este script.
#   scripts/demo.sh <paso>          local (Compose) por defecto
#   HOST=<ip> API_KEY=... CENTRAL_API_KEY=... PORT_WH2=8102 scripts/demo.sh <paso>   contra AWS
# Pasos: salud movimiento cache rabbit global transferencia compensacion caos bodega-caida batch carga
# Los pasos `caos`, `bodega-caida` y `carga` necesitan Docker local; en AWS no hay acceso a la EC2.
set -uo pipefail

cd "$(dirname "$0")/.."
HOST=${HOST:-localhost}
API_KEY=${API_KEY:-dev-api-key}
CENTRAL_API_KEY=${CENTRAL_API_KEY:-dev-central-key}
PORT_WH1=${PORT_WH1:-8101}
PORT_WH2=${PORT_WH2:-8080}   # local: WH-002 va por nginx; en AWS es el 8102
PORT_WH3=${PORT_WH3:-8103}
PORT_CENTRAL=${PORT_CENTRAL:-8004}
PORT_RABBIT=${PORT_RABBIT:-15672}
SUFIJO=${SUFIJO:-$(date +%H%M%S)}

wh1() { curl -s -m 10 "$@" -H "X-API-Key: $API_KEY"; }
central() { curl -s -m 10 "$@" -H "X-API-Key: $CENTRAL_API_KEY"; }
dc() {
  docker compose -p warehouses-demo -f infrastructure/compose/compose.distributed.yml \
    -f infrastructure/compose/compose.central.yml -f infrastructure/compose/compose.obs.yml --profile obs "$@"
}
json_line() { python3 -c "import sys,json
for l in sys.stdin:
    d=json.loads(l)
    $1"; }
titulo() { printf '\n== %s ==\n' "$1"; }
json() { python3 -c "import sys,json;d=json.load(sys.stdin);$1"; }

crear_transferencia() { # <origen> <destino> <sku> <cantidad> <llave> -> imprime el id
  central -X POST "http://$HOST:$PORT_CENTRAL/transfers" -H "Idempotency-Key: $5" -H "X-Correlation-ID: COR-DEMO-$5" \
    -H 'Content-Type: application/json' \
    -d "{\"source_warehouse_id\":\"$1\",\"destination_warehouse_id\":\"$2\",\"sku\":\"$3\",\"quantity\":$4}" \
    | json "print(d['transfer_id'])"
}
mostrar_transferencia() { # <id>
  for _ in $(seq 1 20); do
    central "http://$HOST:$PORT_CENTRAL/transfers/$1" > /tmp/demo-transfer.json
    estado=$(json "print(d['status'])" < /tmp/demo-transfer.json)
    case "$estado" in COMPLETED|CANCELLED|FAILED) break ;; esac
    sleep 1
  done
  json "print('estado :', d['status'], d.get('reason') or ''); print('historia:', ' -> '.join(h['new_status'] for h in d['history']))" < /tmp/demo-transfer.json
}
stock() { # <puerto> <sku> <etiqueta>
  wh1 "http://$HOST:$1/inventory/$2" | json "print('$3', '$2 =', d['quantity'], '(reservado', d['reserved_quantity'], ', versión', d['version'], ')')"
}

paso=${1:?uso: scripts/demo.sh <salud|movimiento|cache|rabbit|global|transferencia|compensacion|caos|bodega-caida|batch|carga>}

case "$paso" in
  salud)
    titulo "Salud de las tres bodegas, la central y una transferencia de punta a punta"
    API_KEY=$API_KEY CENTRAL_API_KEY=$CENTRAL_API_KEY PORT_WH2=$PORT_WH2 scripts/smoke.sh "$HOST"
    ;;
  movimiento)
    titulo "Movimiento de inventario en WH-001 (entra una unidad de P-001)"
    stock "$PORT_WH1" P-001 "antes  :"
    wh1 -X POST "http://$HOST:$PORT_WH1/inventory/movements" -H "X-Correlation-ID: COR-DEMO-MOV-$SUFIJO" \
      -H 'Content-Type: application/json' -d '{"sku":"P-001","type":"RECEIPT","quantity":1,"reference":"demo"}' \
      | json "print('movimiento', d['id'], d['type'], d['quantity'], 'en', d['warehouse_id'])"
    stock "$PORT_WH1" P-001 "después:"
    ;;
  cache)
    titulo "Caché de WH-001: tras escribir, la primera lectura es MISS y la segunda HIT"
    wh1 -X POST "http://$HOST:$PORT_WH1/inventory/movements" -H 'Content-Type: application/json' \
      -d '{"sku":"P-001","type":"RECEIPT","quantity":1,"reference":"demo-cache"}' >/dev/null
    echo "(movimiento registrado: invalida la caché)"
    for i in 1 2; do
      curl -s -m 10 -o /dev/null -D - "http://$HOST:$PORT_WH1/inventory/P-001" -H "X-API-Key: $API_KEY" | grep -i '^x-cache' | sed "s/^/lectura $i: /"
    done
    ;;
  rabbit)
    titulo "Eventos en RabbitMQ (API de administración, guest/guest)"
    curl -s -m 10 -u guest:guest "http://$HOST:$PORT_RABBIT/api/overview" \
      | json "m=d['message_stats']; print('RabbitMQ', d['rabbitmq_version'], '| publicados:', m['publish'], '| entregados con ack:', m.get('deliver_get', 0))"
    curl -s -m 10 -u guest:guest "http://$HOST:$PORT_RABBIT/api/queues" \
      | json "print(*sorted(f\"{q['name']}: {q['messages']} en cola, {q['consumers']} consumidor(es)\" for q in d if q['name'].startswith(('wh-001','central'))), sep='\n')"
    echo "Consola web: http://$HOST:$PORT_RABBIT (guest / guest)"
    ;;
  global)
    titulo "Vista global de P-001 (proyección de la central)"
    sleep 4   # la proyección se actualiza con los eventos de las bodegas
    central "http://$HOST:$PORT_CENTRAL/global/inventory/P-001" \
      | json "print('total:', d['total_quantity']); [print(' ', w['warehouse_id'], w['quantity'], 'versión', w['version'], 'desactualizada' if w['stale'] else 'al día') for w in d['warehouses']]"
    ;;
  transferencia)
    titulo "Transferencia de 10 unidades de P-001 de WH-001 a WH-002 (Saga)"
    stock "$PORT_WH1" P-001 "WH-001 antes  :"; stock "$PORT_WH2" P-001 "WH-002 antes  :"
    id=$(crear_transferencia WH-001 WH-002 P-001 10 "t-$SUFIJO")
    echo "transferencia $id (X-Correlation-ID: COR-DEMO-t-$SUFIJO)"
    mostrar_transferencia "$id"
    stock "$PORT_WH1" P-001 "WH-001 después:"; stock "$PORT_WH2" P-001 "WH-002 después:"
    ;;
  compensacion)
    titulo "Fallo provocado: un SKU que solo existe en el origen (compensación)"
    sku="SOLO-$SUFIJO"
    wh1 -X POST "http://$HOST:$PORT_WH1/products" -H 'Content-Type: application/json' -d "{\"sku\":\"$sku\",\"name\":\"Solo en WH-001\",\"unit\":\"unit\"}" >/dev/null
    wh1 -X POST "http://$HOST:$PORT_WH1/inventory/movements" -H 'Content-Type: application/json' -d "{\"sku\":\"$sku\",\"type\":\"RECEIPT\",\"quantity\":40}" >/dev/null
    stock "$PORT_WH1" "$sku" "WH-001 antes  :"
    id=$(crear_transferencia WH-001 WH-002 "$sku" 10 "c-$SUFIJO")
    mostrar_transferencia "$id"
    stock "$PORT_WH1" "$sku" "WH-001 después:"
    ;;
  caos)
    titulo "Fallo provocado: el worker de WH-001 cae después del commit y el mensaje se reentrega (solo local)"
    stock "$PORT_WH1" P-002 "WH-001 antes  :"
    CHAOS_FAIL_STEP=SHIP_TRANSFER:after_commit dc up -d --force-recreate --no-deps wh001_commands >/dev/null 2>&1
    sleep 8
    id=$(crear_transferencia WH-001 WH-003 P-002 5 "k-$SUFIJO")
    sleep 12
    mostrar_transferencia "$id"
    dc logs --no-color wh001_commands 2>/dev/null | grep -oE '"event": "(chaos_fail_injected|command_duplicate)"' | sort | uniq -c
    stock "$PORT_WH1" P-002 "WH-001 después:"
    echo "(se descontaron 5 unidades una sola vez)"
    dc up -d --force-recreate --no-deps wh001_commands >/dev/null 2>&1
    ;;
  bodega-caida)
    titulo "WH-002 caída: las demás siguen respondiendo y la vista global lo marca (solo local)"
    # El latido (WAREHOUSE_HEARTBEAT) lo emite el worker de outbox: se detiene toda la bodega.
    dc stop wh002_api wh002_worker >/dev/null 2>&1
    sleep 2
    for par in "WH-001:$PORT_WH1" "WH-003:$PORT_WH3"; do
      printf '%s responde: HTTP ' "${par%%:*}"; curl -s -m 5 -o /dev/null -w '%{http_code}\n' "http://$HOST:${par#*:}/health"
    done
    printf 'WH-002 (nginx) responde: HTTP '; curl -s -m 5 -o /dev/null -w '%{http_code}\n' "http://$HOST:$PORT_WH2/health"
    echo "esperando ${ESPERA_STALE:-95} s (la central marca una bodega como desactualizada tras 90 s sin latido)..."
    sleep "${ESPERA_STALE:-95}"
    central "http://$HOST:$PORT_CENTRAL/global/warehouses" \
      | json "print(json.dumps(d, ensure_ascii=False, indent=1)[:900])"
    dc start wh002_api wh002_worker >/dev/null 2>&1
    ;;
  batch)
    titulo "Reporte diario: batch -> S3 -> Lambda -> central"
    echo "En AWS (con la EC2 desplegada, ver docs/aws.md), el batch corre contra las APIs públicas y el bucket real;"
    echo "la Lambda se dispara sola al crearse reports/daily/<fecha>/summary.json:"
    echo "  PYTHONPATH=services/batch:services/common WH001_API_URL=http://\$HOST:8101 WH002_API_URL=http://\$HOST:8102 \\"
    echo "  WH003_API_URL=http://\$HOST:8103 API_KEY=... CENTRAL_API_URL=http://\$HOST:8004 CENTRAL_API_KEY=... \\"
    echo "  S3_BUCKET=<bucket> python -m batch.daily_report --date \$(date -u +%F)"
    echo
    echo "Local, con MinIO (la Lambda no corre en local: se prueba con un evento S3 de ejemplo):"
    docker compose --profile storage up -d minio minio-init >/dev/null 2>&1
    sleep 8
    docker compose --profile storage run --rm --no-deps \
      -e WH001_API_URL=http://host.docker.internal:$PORT_WH1 -e WH002_API_URL=http://host.docker.internal:$PORT_WH2 \
      -e WH003_API_URL=http://host.docker.internal:$PORT_WH3 -e CENTRAL_API_URL=http://host.docker.internal:$PORT_CENTRAL \
      batch python -m batch.daily_report --date "$(date -u +%F)" 2>&1 | grep -E 'daily_report_finished' \
      | json_line 'print("batch:", d["status"], "| bodegas faltantes:", d.get("missing_warehouses"), "| correlation_id:", d["correlation_id"])'
    docker compose --profile storage run --rm --no-deps -T --entrypoint sh minio-init -c \
      'mc alias set local http://minio:9000 minioadmin minioadmin >/dev/null && mc ls --recursive local/warehouse-platform' 2>&1 | grep -E 'STANDARD'
    echo
    echo "Lambda con un evento S3 de ejemplo: S3_ENDPOINT_URL=http://localhost:9000 pytest tests/integration/test_report_validator_minio.py"
    docker compose --profile storage down >/dev/null 2>&1
    ;;
  carga)
    titulo "Carga sobre WH-001 con Grafana en vivo (http://localhost:3000, admin / admin) (solo local)"
    mkdir -p /tmp/demo-carga
    docker run --rm --network warehouses-demo_wh001 -v "$PWD/tests/load:/mnt/locust:ro" -v /tmp/demo-carga:/results \
      -e API_KEY="$API_KEY" locustio/locust:2.32.5 -f /mnt/locust/locustfile.py --headless -u 100 -r 50 -t 45s \
      --host http://wh001_api:8000 --csv /results/demo UsuarioBodega 2>&1 | grep -E "Aggregated" | tail -1
    ;;
  *) echo "paso desconocido: $paso" >&2; exit 1 ;;
esac
