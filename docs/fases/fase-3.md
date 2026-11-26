# Fase 3 — RabbitMQ y workers

## Avance D-02 — Conexión y topología

Se añadió RabbitMQ con consola de management y healthcheck a los Compose raíz y distribuido. El paquete `services/common` incluye el cliente `common.rabbit` para conexión con reintento, declaración durable e idempotente de exchanges, colas y bindings, publicación JSON persistente con publisher confirms y consumo con ack manual. El consumidor establece el `correlation_id` en el ContextVar compartido mientras ejecuta el handler y confirma el mensaje solo si el handler retorna correctamente.

Los errores del handler se reencolan por ahora. El límite de reintentos y las DLQ pertenecen a D-05. El consumidor usa `set_correlation_id` y `reset_correlation_id` de J-03 para compartir el mismo contexto con el middleware HTTP.

## Contrato

La topología y los mensajes están documentados en [events.md](../events.md). La decisión de exchanges y entrega está en [ADR-0005](../adr/0005-topologia-rabbitmq.md).

## Evidencia y preguntas

La prueba `tests/integration/test_rabbit.py` publicó y consumió un mensaje real y comprobó el correlation ID dentro del handler: **1 prueba pasada** con Python 3.12 y RabbitMQ 3.13. Se ejecutó en un contenedor unido a la red de Compose.

`rabbitmqctl list_exchanges name type durable` mostró `warehouse.events`, `central.events`, `warehouse.commands`, `iot.readings` y `dlx`. `rabbitmqctl list_queues name durable arguments` mostró las colas del contrato con `x-dead-letter-exchange=dlx`. El servicio `rabbitmq-topology` terminó con código 0.

La consola de management está disponible en `http://localhost:15672` mientras el contenedor está activo. Las preguntas del profesor de F3 se completarán al integrar D-03 y D-04.

## D-03 — Outbox y heartbeat

Cada movimiento inserta `INVENTORY_UPDATED` en `outbox` dentro de su transacción. El worker publica filas pendientes con confirmación, reintenta con backoff cuando falla RabbitMQ y emite `WAREHOUSE_HEARTBEAT` cada 30 segundos. La migración está en `infrastructure/sql/warehouse/migrations/001_outbox.sql`; el ADR asociado es [ADR-0006](../adr/0006-patron-outbox.md).

La prueba `tests/integration/test_outbox_relay.py` publicó un evento desde PostgreSQL a RabbitMQ y confirmó su `published_at`. El conjunto de pruebas unitarias de J-03 y las pruebas de integración RabbitMQ/outbox terminó con **19 pruebas pasadas** en Python 3.12.

Se verificó también la recuperación real en Compose: con RabbitMQ detenido, `POST /inventory/movements` para `P-001` respondió **201** y la fila `INVENTORY_UPDATED` permaneció en el outbox pendiente (`attempts=1`). Después de reiniciar RabbitMQ, el worker la publicó con confirmación y la fila quedó con `published_at` no nulo (`attempts=2`); el outbox quedó sin pendientes. El mismo worker volvió a publicar el heartbeat.

## D-04 — Invalidación asíncrona, auditoría y reportes

- La API invalida Redis sincrónicamente por defecto. Con `CACHE_INVALIDATION=async`, registra el evento en el outbox y omite el `DEL` síncrono; `cache-invalidation-worker` consume `wh-00X.cache-invalidation` y borra la llave. Si Redis no está disponible, el handler falla para que RabbitMQ reencole el mensaje.
- El worker central consume `central.audit` y escribe el sobre en `audit_events`; `event_id` es la clave primaria y `ON CONFLICT DO NOTHING` hace idempotente la inserción.
- `POST /reports` acepta un rango UTC (`start_at`, `end_at`), crea `report_jobs` y `REPORT_REQUESTED` en la misma transacción, y responde HTTP 202 con `job_id` y estado `PROCESSING`.
- El worker de reportes calcula conteos y unidades movidas por tipo, además de los diez SKU más movidos (suma de valores absolutos), y guarda `DONE`/resultado o `FAILED`/error. `GET /reports/jobs/{id}` consulta el estado. Con `REPORTS_TO_S3=true` el resultado también se escribe en `reports/jobs/<job_id>.json` (J-08, ver [fase 8](fase-8.md)).
- Los consumidores reutilizan el `correlation_id` del sobre; el formatter JSON lo incluye en los logs de API y workers.

La tabla `report_jobs` está en `schema.sql` y en la migración `002_report_jobs.sql`. Para un volumen de base ya creado, ejecutar una vez `docker compose exec db psql -U admin -d platform -v ON_ERROR_STOP=1 -f /sql/migrations/002_report_jobs.sql`.

Evidencia automatizada: `tests/integration/fase3/test_d04_warehouse.py` cubre la API/outbox, el procesamiento repetido del reporte, el borrado de Redis y el consumo de un mensaje pendiente; `tests/integration/fase3/central_audit/test_d04_audit.py` verifica la deduplicación de auditoría. El workflow `Fase 3 - Workers` levanta PostgreSQL, Redis y RabbitMQ para estos casos.
