# ADR-0006: Publicación de eventos con outbox transaccional

- Estado: Aceptado.
- Fecha: 22 de noviembre de 2026.
- Autor: David.

## Contexto

Un movimiento de inventario debe persistirse en PostgreSQL aunque RabbitMQ esté temporalmente caído. Publicar directamente después del commit puede perder el evento si el proceso se detiene entre ambas operaciones; publicar antes del commit puede emitir un evento para un movimiento que luego se revierte.

## Alternativas

1. Publicar directamente desde la API antes o después del commit.
2. Escribir el evento en una tabla outbox dentro de la transacción del movimiento y publicarlo después desde un worker.
3. Usar una transacción distribuida entre PostgreSQL y RabbitMQ.

## Decisión

Usar una tabla `outbox` en la misma base de la bodega. La API inserta el movimiento, actualiza inventario y agrega `INVENTORY_UPDATED` en una sola transacción. El worker reclama filas pendientes con `FOR UPDATE SKIP LOCKED`, publica con publisher confirms y solo entonces marca `published_at`.

## Consecuencias

- Si RabbitMQ no está disponible, la operación de inventario se confirma y el evento queda pendiente para reintento.
- La publicación es al menos una vez: una caída después del confirm pero antes de marcar la fila puede generar duplicados. Los consumidores deben ser idempotentes usando `event_id` o `version`.
- El relay mantiene un bloqueo de fila mientras publica; los lotes se limitan a 100 mensajes para acotar el tiempo de transacción.
- El worker también publica un heartbeat cada 30 segundos. Si RabbitMQ se cae, lo intenta de nuevo al reconectarse.
