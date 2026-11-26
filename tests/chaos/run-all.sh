#!/usr/bin/env bash
set -Eeuo pipefail
root="$(cd "$(dirname "$0")/../.." && pwd)"
project="${D06_COMPOSE_PROJECT:-d06-chaos}"
export D06_COMPOSE_PROJECT="$project"
export D06_KEEP_STACK=true
scripts=(
  caso-1-redis.sh
  caso-2-rabbitmq.sh
  caso-3-worker.sh
  caso-4-duplicado.sh
  caso-5-bodega.sh
)
cleanup() {
  docker compose -p "$project" \
    -f "$root/infrastructure/compose/compose.distributed.yml" \
    -f "$root/infrastructure/compose/compose.central.yml" \
    -f "$root/tests/chaos/compose.d06-ports.yml" down
}
trap cleanup EXIT
for script in "${scripts[@]}"; do
  bash "$root/tests/chaos/$script"
done
