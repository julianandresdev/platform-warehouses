# Fase 1 — API + PostgreSQL

Líder: Julian · Apoyo: Esteban

## Qué se construyó

- `docker-compose.yaml`: levanta PostgreSQL 16 y la API; la API espera a que la base esté saludable.
- `Dockerfile`: imagen de la API (Python 3.12, uvicorn en el puerto 8000).
- API en FastAPI: CRUD de productos con SKU único, consulta de inventario y movimientos `RECEIPT` / `SHIPMENT`.
- Los movimientos se procesan en una transacción con `SELECT ... FOR UPDATE` para que el stock nunca quede negativo.
- `.env.example`: variables de entorno (`DATABASE_URL`, `SQL_ECHO`).
- `requirements.txt`: todas las dependencias de la API.

## Pendiente para cerrar la fase

- [ ] `schema.sql` como fuente de verdad (montado en `/docker-entrypoint-initdb.d/`), sin `create_all`.
- [ ] `UNIQUE (product_id, warehouse_id)` en `inventory` e `INSERT ... ON CONFLICT DO NOTHING` antes del bloqueo.
- [ ] `CHECK` de cantidades en la base.
- [ ] `WAREHOUSE_ID` de tipo texto (`WH-001`) leído del entorno, no del body.
- [ ] 409 para stock insuficiente, SKU duplicado y DELETE de un producto con movimientos.
- [ ] Tipo de movimiento `ADJUSTMENT`.
- [ ] Pruebas unitarias y de integración (incluida la de 2 salidas concurrentes de 6 sobre stock 10).
- [ ] Colección `.http` con las pruebas del README.

## Decisiones

| Decisión | Elegido | Por qué |
| --- | --- | --- |
| Puerto de la API | 8000 | En macOS el Receptor AirPlay ocupa el 5000 |
| Tipo de `warehouse_id` | Texto (`WH-001`) | Coincide con el enunciado, las llaves de Redis y las routing keys de RabbitMQ |
| DELETE de producto con movimientos | 409 Conflict | Más simple que el borrado lógico y no complica el SKU único |

## Preguntas del profesor

<!-- Responder cada pregunta del enunciado de la Fase 1 con evidencia (capturas, logs, salidas de pruebas). -->

## Evidencia

<!-- Capturas, salidas de pytest, logs. -->
