#!/usr/bin/env bash
# Escenarios de carga de la F11 (J-09). Cada uno corre Locust headless con --csv y,
# a mitad de la corrida, guarda `docker stats` y capturas de Grafana en
# docs/evidencias/fase-11/<escenario>/.
#
# Requisitos: las tres bodegas, la central y la observabilidad arriba:
#   docker compose -p warehouses-demo \
#     -f infrastructure/compose/compose.distributed.yml -f infrastructure/compose/compose.central.yml \
#     -f infrastructure/compose/compose.obs.yml -f infrastructure/compose/compose.load.yml \
#     --profile obs up -d --build
#
# Uso: scripts/fase-11/correr.sh <escenario>
#   redis-off | redis-on | wh002-1-instancia | wh002-3-instancias | multibodega | rampa-100 | rampa-500 | rampa-1000 | rampa-5000
# Variables: DURACION (segundos, por defecto 90), CHROME (ruta al ejecutable).
set -euo pipefail

cd "$(dirname "$0")/../.."
PROYECTO=warehouses-demo
DURACION=${DURACION:-90}
CHROME=${CHROME:-"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"}
API_KEY=${API_KEY:-dev-api-key}
LOCUST_IMAGE=locustio/locust:2.32.5
ESC=${1:?escenario requerido}
OUT=docs/evidencias/fase-11/$ESC
mkdir -p "$OUT"

dc() {
  docker compose -p $PROYECTO \
    -f infrastructure/compose/compose.distributed.yml -f infrastructure/compose/compose.central.yml \
    -f infrastructure/compose/compose.obs.yml -f infrastructure/compose/compose.load.yml \
    --profile obs "$@"
}

esperar_api() { # <puerto en el host>
  for _ in $(seq 1 60); do
    curl -fsS "http://localhost:$1/health" >/dev/null 2>&1 && return 0
    sleep 2
  done
  echo "La API en el puerto $1 no respondió" >&2; return 1
}

# lanzar_locust <nombre> <red> <host> <usuarios> <rampa/s> <escenario locust> <procesos> [espera]
lanzar_locust() {
  local nombre=$1 red=$2 host=$3 usuarios=$4 rampa=$5 clase=$6 procesos=$7 espera=${8:-0.05}
  docker rm -f "locust-$nombre" >/dev/null 2>&1 || true
  docker run -d --rm --name "locust-$nombre" --network "${PROYECTO}_$red" \
    -v "$PWD/tests/load:/mnt/locust:ro" -v "$PWD/$OUT:/results" \
    -e API_KEY="$API_KEY" -e LOAD_WAIT="$espera" "$LOCUST_IMAGE" \
    -f /mnt/locust/locustfile.py --headless -u "$usuarios" -r "$rampa" -t "${DURACION}s" \
    --processes "$procesos" --host "$host" --csv "/results/$nombre" "$clase" >/dev/null
}

# Recrea las réplicas de WH-002 y nginx antes de cada escenario: tras una sobrecarga las
# réplicas pueden quedar atascadas (conexiones "idle in transaction") y la corrida siguiente
# mediría ese atasco y no la capacidad (ver docs/evidencias/fase-11/sin-reinicio-entre-escenarios/).
reiniciar_wh002() { # <réplicas>
  dc up -d --force-recreate --no-deps --scale wh002_api="$1" wh002_api >/dev/null 2>&1
  sleep 20
  dc up -d --force-recreate --no-deps nginx >/dev/null 2>&1
  sleep 4
}

esperar_locust() {
  while docker ps --format '{{.Names}}' | grep -q '^locust-'; do sleep 2; done
}

capturar() { # a mitad de la corrida
  sleep $((DURACION / 2))
  docker stats --no-stream --format 'table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.MemPerc}}' > "$OUT/docker-stats.txt"
  for d in apis redis rabbitmq workers saga; do
    "$CHROME" --headless=new --disable-gpu --hide-scrollbars --window-size=1400,1050 \
      --virtual-time-budget=25000 --screenshot="$PWD/$OUT/grafana-$d.png" \
      "http://localhost:3000/d/wp-$d?orgId=1&from=now-3m&to=now&kiosk" >/dev/null 2>&1 || true
  done
}


case "$ESC" in
  redis-off|redis-on)
    [ "$ESC" = redis-off ] && export CACHE_ENABLED=false || export CACHE_ENABLED=true
    dc up -d --force-recreate --no-deps wh001_api; esperar_api 8101
    lanzar_locust "$ESC" wh001 http://wh001_api:8000 100 100 ReadSameSku 1 0
    capturar; esperar_locust
    CACHE_ENABLED=true dc up -d --force-recreate --no-deps wh001_api >/dev/null
    ;;
  wh002-1-instancia|wh002-3-instancias)
    n=1; [ "$ESC" = wh002-3-instancias ] && n=3
    reiniciar_wh002 $n
    lanzar_locust "$ESC" wh002 http://nginx:80 200 100 UsuarioBodega 1
    capturar; esperar_locust
    ;;
  multibodega)
    reiniciar_wh002 3
    lanzar_locust wh001 wh001 http://wh001_api:8000 50 50 UsuarioBodega 1
    lanzar_locust wh002 wh002 http://nginx:80 800 200 UsuarioBodega 2
    lanzar_locust wh003 wh003 http://wh003_api:8000 20 20 UsuarioBodega 1
    capturar; esperar_locust
    ;;
  rampa-*)
    u=${ESC#rampa-}; procesos=1; [ "$u" -ge 1000 ] && procesos=4
    reiniciar_wh002 3
    lanzar_locust "$ESC" wh002 http://nginx:80 "$u" $((u / 5 > 50 ? u / 5 : 50)) UsuarioBodega "$procesos"
    capturar; esperar_locust
    ;;
  *) echo "escenario desconocido: $ESC" >&2; exit 1 ;;
esac

echo "Listo: $OUT"
ls "$OUT"
