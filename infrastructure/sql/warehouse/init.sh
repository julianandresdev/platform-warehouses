#!/bin/sh
# Se monta en /docker-entrypoint-initdb.d/ del contenedor de PostgreSQL.
# Aplica, en orden: schema.sql, migrations/*.sql y seed/${WAREHOUSE_ID}.sql.
# Solo corre cuando el volumen de datos esta vacio: para reaplicar los cambios,
# recrear la base con `make reset-db`.
set -e

SQL_DIR=/sql
PSQL="psql -v ON_ERROR_STOP=1 --username $POSTGRES_USER --dbname $POSTGRES_DB"

echo "init: schema.sql"
$PSQL -f "$SQL_DIR/schema.sql"

for f in $(ls "$SQL_DIR"/migrations/*.sql 2>/dev/null | sort); do
    echo "init: migracion $(basename "$f")"
    $PSQL -f "$f"
done

SEED="$SQL_DIR/seed/${WAREHOUSE_ID}.sql"
if [ -n "$WAREHOUSE_ID" ] && [ -f "$SEED" ]; then
    echo "init: seed ${WAREHOUSE_ID}"
    $PSQL -f "$SEED"
else
    echo "init: sin seed para WAREHOUSE_ID='${WAREHOUSE_ID}'"
fi
