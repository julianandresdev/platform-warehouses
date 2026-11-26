#!/bin/sh
# Inicializa la base de WH-001 en RDS: schema.sql, migraciones y seed, solo si la tabla
# `products` no existe todavía (repetirlo no hace nada). Lo ejecuta el servicio
# wh001_db_init de docker-compose.yaml. DATABASE_URL llega con el driver de SQLAlchemy.
set -eu

WAREHOUSE_ID=${1:?WAREHOUSE_ID requerido}
URL=$(echo "$DATABASE_URL" | sed 's/+psycopg2//')
PSQL="psql -v ON_ERROR_STOP=1 $URL"

for _ in $(seq 1 30); do
  pg_isready -d "$URL" >/dev/null 2>&1 && break
  sleep 5
done

if [ "$($PSQL -tA -c "SELECT to_regclass('public.products') IS NOT NULL")" = "t" ]; then
  echo "init-rds: la base ya está inicializada"
  exit 0
fi

echo "init-rds: schema.sql"
$PSQL -f /sql/schema.sql
for f in $(ls /sql/migrations/*.sql 2>/dev/null | sort); do
  echo "init-rds: migración $(basename "$f")"
  $PSQL -f "$f"
done
echo "init-rds: seed $WAREHOUSE_ID"
$PSQL -f "/sql/seed/$WAREHOUSE_ID.sql"
