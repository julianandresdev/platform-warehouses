# ADR-0003: `schema.sql` como fuente de verdad del esquema, con reglas en la base

- Estado: aceptado
- Fecha: 2026-11-22
- Autor: Julian

## Contexto

Hasta ahora las tablas salían de `Base.metadata.create_all` al arrancar la API. Eso tiene tres problemas:

1. Con varias bodegas y réplicas, cada API intenta crear las tablas al mismo tiempo.
2. `create_all` no cambia tablas que ya existen: un cambio de esquema solo se ve con una base nueva.
3. Las reglas de negocio (stock no negativo, una fila de inventario por producto y bodega) vivían solo en Python. Un error de código, un script manual o una carrera entre peticiones podía dejar datos inválidos.

El enunciado de la Fase 1 además pide `schema.sql` como entregable.

## Alternativas

| Alternativa | A favor | En contra |
| --- | --- | --- |
| **`schema.sql` + migraciones SQL montados en PostgreSQL** | Una sola fuente; el esquema se aplica antes de que arranque la API; sirve para cualquier lenguaje | Solo corre con el volumen vacío; los cambios posteriores se escriben a mano |
| Alembic | Migraciones versionadas y reversibles | Otra herramienta y otro paso de arranque; la API tendría que esperar a migrar |
| Mantener `create_all` | Cero configuración | Las dos fuentes (SQL y modelos) terminan en esquemas distintos; no hay restricciones fuertes |

## Decisión

- `infrastructure/sql/warehouse/schema.sql` define el esquema; `migrations/NNN_*.sql` los cambios posteriores y `seed/<WAREHOUSE_ID>.sql` los datos de prueba.
- `init.sh` los aplica en ese orden desde `/docker-entrypoint-initdb.d/` del contenedor de PostgreSQL. Se elimina `create_all`.
- Las reglas viven en la base:
  - `UNIQUE (product_id, warehouse_id)` en `inventory`.
  - `CHECK (quantity >= 0)` y `CHECK (reserved_quantity >= 0 AND reserved_quantity <= quantity)`.
  - `CHECK (quantity <> 0)` en `inventory_movements`.
  - Llaves foráneas `ON DELETE RESTRICT`.
  - Columna `version` en `inventory`, que sube en 1 con cada cambio.
- `models.py` refleja el SQL; si cambia una tabla, se cambia primero el SQL.
- La API traduce los códigos de PostgreSQL a HTTP: `23505` (único) y `23001`/`23503` (llave foránea) se convierten en 409.

## Consecuencias

- Para aplicar un cambio en `schema.sql`, `migrations/` o `seed/` hay que recrear el volumen: `make reset-db` (borra los datos locales).
- La base es la última línea de defensa: aunque la API tenga un error, no puede quedar stock negativo ni dos filas de inventario para el mismo producto en la misma bodega.
- Cada bodega, con su propia base, aplica el mismo esquema y su propia semilla.
- Con `RESTRICT`, PostgreSQL responde `23001` y no `23503` al borrar una fila referenciada; la API contempla ambos.
