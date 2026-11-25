# ADR-0020 — Idempotencia de los comandos de la Saga en la bodega

## Estado

Aceptado (J-07, F6).

## Contexto

RabbitMQ entrega al menos una vez: un comando puede llegar repetido si el worker
muere entre el commit y el ack, y la central puede reenviar un paso (otro
`event_id`) tras un reinicio o un timeout. Repetir una reserva o una salida
descuadra el inventario.

## Alternativas

1. **Solo `processed_messages` por `event_id`.** Simple y exigido por el plan, pero
   no cubre un reenvío del mismo paso con un `event_id` nuevo.
2. **Tabla de estado por transferencia en la bodega** (`transfer_id`, estado). Cubre
   ambos casos, pero duplica en la bodega una máquina de estados que ya vive en la
   central.
3. **`processed_messages` + movimientos marcados con `reference = transfer:<id>`.**
   El historial de movimientos, que ya existe, dice qué pasos se aplicaron.

## Decisión

Opción 3. El primer paso de la transacción inserta `(message_id, consumer)` en
`processed_messages` (PK compuesta); si choca, ack sin efecto. Con la fila de
inventario bloqueada, el handler consulta los movimientos de esa transferencia y,
si el paso ya está, solo vuelve a emitir la respuesta.

Los movimientos de la Saga son tipos nuevos de `movement_type` (`RESERVATION`,
`RESERVATION_RELEASE`, `TRANSFER_OUT`, `TRANSFER_IN`, `TRANSFER_RETURN`) en vez de
reutilizar `SHIPMENT`/`RECEIPT`, para que el historial distinga una venta de una
transferencia y la reserva quede registrada aunque no cambie `quantity`. La API
sigue aceptando solo `RECEIPT`, `SHIPMENT` y `ADJUSTMENT` en `POST /inventory/movements`.

## Consecuencias

- Un duplicado nunca mueve stock dos veces, venga con el mismo `event_id` o con otro.
- `processed_messages` crece con cada comando; habrá que purgar filas viejas si el
  volumen lo pide (no es necesario para el proyecto).
- Las respuestas repetidas son posibles; la central ya deduplica eventos por
  `event_id` y descarta transiciones incompatibles (E-06).
- Agregar valores a un `ENUM` de PostgreSQL no se puede deshacer fácilmente; se
  acepta porque los tipos son parte del dominio.
