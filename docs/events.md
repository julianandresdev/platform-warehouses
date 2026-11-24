# Contrato de eventos y comandos

Versión 1 · 22 de noviembre de 2026 · Responsable: David

Este documento fija el contrato de mensajes para los servicios del proyecto. Se deriva del plan de desarrollo adjunto. Describe el contrato objetivo; no implica que todos los productores, consumidores o workers estén implementados todavía. Los cambios posteriores deben actualizar este archivo junto con el código que los usa.

## Sobre común

Todos los eventos y comandos se serializan como JSON UTF-8 y usan este sobre:

```json
{
  "event_id": "9b1c8a0e-95d8-4df2-a408-13673c61520d",
  "event_type": "INVENTORY_UPDATED",
  "event_version": 1,
  "occurred_at": "2026-11-18T15:00:00Z",
  "correlation_id": "COR-20261118-3fa2b1c4",
  "source": "warehouse-WH-001",
  "payload": {
    "warehouse_id": "WH-001",
    "sku": "LAPTOP-001",
    "quantity": 90,
    "reserved_quantity": 0,
    "version": 17
  }
}
```

| Campo | Tipo | Regla |
| --- | --- | --- |
| `event_id` | string UUID v4 | Identifica una publicación lógica; se conserva en cada reintento. |
| `event_type` | string | Nombre del evento o comando en mayúsculas. |
| `event_version` | integer | Versión del esquema del tipo de mensaje; inicia en `1`. |
| `occurred_at` | string fecha-hora | ISO 8601 en UTC, terminado en `Z`. |
| `correlation_id` | string | Se propaga desde `X-Correlation-ID`; si falta, lo genera el middleware. |
| `source` | string | Servicio emisor; las bodegas usan `warehouse-WH-00X`. |
| `payload` | object | Datos propios del tipo, documentados abajo. |

Un comando usa el mismo sobre. Para comandos, `event_id` identifica el comando y `event_type` contiene su nombre. La versión del sobre no cambia por los reintentos.

## Propiedades AMQP

Las publicaciones usan `message_id = event_id`, `correlation_id` del sobre, `content_type = application/json` y `delivery_mode = 2` (persistente). El header entero `x-attempt` empieza en `0` y aumenta al republicar por un error transitorio. Los productores del patrón outbox publican solo después del commit de la transacción de negocio. Las colas son durables y los consumidores usan `prefetch_count = 10`, ack manual tras confirmar el efecto y su registro idempotente en la base.

## Exchanges

| Exchange | Tipo | Uso |
| --- | --- | --- |
| `warehouse.events` | topic | Eventos originados en bodegas. |
| `central.events` | topic | Eventos originados en la central. |
| `warehouse.commands` | direct | Comandos dirigidos a una bodega, con routing key igual a `warehouse_id`. |
| `iot.readings` | topic | Lecturas validadas que entrega el gateway IoT. |
| `dlx` | direct | Dead-letter exchange para mensajes que no pueden procesarse. |

Cada servicio declara, al iniciar, los exchanges y colas que utiliza. `declare_topology()` debe ser idempotente. Las colas de trabajo son durables y configuran `x-dead-letter-exchange = dlx`. Para F10, cada cola de trabajo tendrá además una cola `<cola>.retry` con TTL de 5000 ms y una `<cola>.dlq`; la política de reintentos y el routing de DLQ se especifican en la sección F10 de este documento cuando quede implementada.

## Catálogo de eventos

En las tablas, `WH` representa un identificador de bodega como `WH-001`. Las claves se sustituyen con el valor real, por ejemplo `warehouse.WH-001.inventory.updated`.

| Tipo | Emisor / exchange | Routing key | Payload requerido | Consumidores | Idempotencia natural |
| --- | --- | --- | --- | --- | --- |
| `INVENTORY_UPDATED` | Bodega / `warehouse.events` | `warehouse.WH.inventory.updated` | `warehouse_id: string`, `sku: string`, `quantity: integer`, `reserved_quantity: integer`, `version: integer`, `movement_type: string` | Invalidación de caché de la bodega, proyección central, auditoría | La proyección descarta `version` repetida o menor; borrar una clave de caché se puede repetir. Auditoría deduplica por `event_id`. |
| `WAREHOUSE_HEARTBEAT` | Bodega / `warehouse.events` | `warehouse.WH.heartbeat` | `warehouse_id: string` | Proyección central | Actualizar `last_seen` es repetible; se conserva el timestamp más reciente. |
| `REPORT_REQUESTED` | Bodega / `warehouse.events` | `warehouse.WH.report.requested` | `job_id: string (UUID)`, `warehouse_id: string`, `parameters: object` | Worker de reportes de esa bodega | El worker debe deduplicar por `event_id` o `job_id`. |
| `STOCK_RESERVED` | Bodega / `warehouse.events` | `warehouse.WH.transfer.stock_reserved` | `transfer_id: string (UUID)`, `warehouse_id: string`, `sku: string`, `quantity: integer` | Orquestador central, auditoría | Auditoría deduplica por `event_id`; el orquestador registra el mensaje procesado. |
| `STOCK_RESERVATION_FAILED` | Bodega / `warehouse.events` | `warehouse.WH.transfer.stock_reservation_failed` | `transfer_id: string (UUID)`, `warehouse_id: string`, `sku: string`, `quantity: integer`, `reason: string` | Orquestador central, auditoría | Igual que los demás resultados de transferencia. |
| `RESERVATION_RELEASED` | Bodega / `warehouse.events` | `warehouse.WH.transfer.reservation_released` | `transfer_id: string (UUID)`, `warehouse_id: string`, `sku: string`, `quantity: integer` | Orquestador central, auditoría | Igual que los demás resultados de transferencia. |
| `TRANSFER_SHIPPED` | Bodega / `warehouse.events` | `warehouse.WH.transfer.transfer_shipped` | `transfer_id: string (UUID)`, `warehouse_id: string`, `sku: string`, `quantity: integer` | Orquestador central, auditoría | Igual que los demás resultados de transferencia. |
| `TRANSFER_RECEIVED` | Bodega / `warehouse.events` | `warehouse.WH.transfer.transfer_received` | `transfer_id: string (UUID)`, `warehouse_id: string`, `sku: string`, `quantity: integer` | Orquestador central, auditoría | Igual que los demás resultados de transferencia. |
| `TRANSFER_RECEIVE_FAILED` | Bodega / `warehouse.events` | `warehouse.WH.transfer.transfer_receive_failed` | `transfer_id: string (UUID)`, `warehouse_id: string`, `sku: string`, `quantity: integer`, `reason: string` | Orquestador central, auditoría | Igual que los demás resultados de transferencia. |
| `STOCK_RETURNED` | Bodega / `warehouse.events` | `warehouse.WH.transfer.stock_returned` | `transfer_id: string (UUID)`, `warehouse_id: string`, `sku: string`, `quantity: integer` | Orquestador central, auditoría | Igual que los demás resultados de transferencia. |
| `TRANSFER_STATUS_CHANGED` | Central / `central.events` | `central.transfer.status_changed` | `transfer_id: string (UUID)`, `from: string`, `to: string` | Auditoría | Auditoría deduplica por `event_id`. |
| `REPORT_REGISTERED` | Central (disparado por Lambda) / `central.events` | `central.report.registered` | `key: string`, `size: integer`, `checksum: string` | Auditoría | Auditoría deduplica por `event_id`; el registro usa la llave del objeto. |
| `SENSOR_READING` | Gateway IoT / `iot.readings` | `iot.WH.<sensor_type>` | `warehouse_id: string`, `sensor_id: string`, `sensor_type: string`, `value: number`, `sequence_number: integer`, `timestamp: string ISO 8601`, `event_id: string UUID` | Almacenamiento IoT; alertas para temperatura | Almacenamiento deduplica por `event_id`; estado solo avanza a una secuencia mayor. |
| `SENSOR_ALERT` | Worker de alertas IoT / `iot.readings` | `iot.WH.temperature.alert` | `warehouse_id: string`, `sensor_id: string`, `sensor_type: string`, `value: number`, `threshold: number`, `sequence_number: integer`, `timestamp: string ISO 8601` | Consumidores de alertas (por definir) | No repetir la misma alerta activa para sensor y regla. |

Los mensajes de transferencia llevan el `correlation_id` de la solicitud que inició la Saga. El orquestador usa `transfer_id` para asociar resultados y conserva idempotencia por mensaje en `processed_messages`.

## Catálogo de comandos

Los comandos salen de la central por `warehouse.commands` con routing key igual al destino (`WH-001`). Todos incluyen `transfer_id: string (UUID)`, `sku: string`, `quantity: integer` y `warehouse_id: string`; `RESERVE_STOCK` incluye además `deadline: string ISO 8601 UTC`. El sobre lleva el tipo indicado en `event_type`.

| Comando | Destino | Resultado esperado | Consumidor | Idempotencia |
| --- | --- | --- | --- | --- |
| `RESERVE_STOCK` | Bodega origen | `STOCK_RESERVED` o `STOCK_RESERVATION_FAILED` | Worker de comandos de la bodega | Registrar `(event_id, consumer)` junto con la reserva. |
| `RELEASE_RESERVATION` | Bodega origen | `RESERVATION_RELEASED` | Worker de comandos de la bodega | Registrar comando y liberación en una transacción. |
| `SHIP_TRANSFER` | Bodega origen | `TRANSFER_SHIPPED` | Worker de comandos de la bodega | Registrar comando junto con la salida de stock. |
| `RECEIVE_TRANSFER` | Bodega destino | `TRANSFER_RECEIVED` o `TRANSFER_RECEIVE_FAILED` | Worker de comandos de la bodega | Registrar comando junto con la entrada de stock. |
| `RETURN_STOCK` | Bodega origen | `STOCK_RETURNED` | Worker de comandos de la bodega | Registrar comando junto con el movimiento compensatorio. |

Valores de `reason` que emite la bodega (J-07): `STOCK_RESERVATION_FAILED` usa `DEADLINE_EXCEEDED`, `INSUFFICIENT_STOCK` o `SKU_NOT_FOUND`; `TRANSFER_RECEIVE_FAILED` usa `SKU_NOT_FOUND`. Cada paso que cambia el inventario emite también `INVENTORY_UPDATED` con `movement_type` igual a `RESERVATION`, `RESERVATION_RELEASE`, `TRANSFER_OUT`, `TRANSFER_IN` o `TRANSFER_RETURN`. El detalle está en [distributed-transactions.md](distributed-transactions.md).

## Colas y bindings

Todas son durables, tienen `prefetch_count = 10`, ack manual después del commit y dead-letter hacia `dlx`.

| Cola | Binding | Consumidor |
| --- | --- | --- |
| `wh-001.commands` | `warehouse.commands` con routing key `WH-001` | Worker de comandos de WH-001. Una cola equivalente por bodega. |
| `wh-001.cache-invalidation` | `warehouse.events` con `warehouse.WH-001.inventory.updated` | Worker de invalidación asíncrona de WH-001 (cuando `CACHE_INVALIDATION=async`). |
| `wh-001.reports` | `warehouse.events` con `warehouse.WH-001.report.requested` | Worker de reportes de WH-001. |
| `central.projection` | `warehouse.events` con `warehouse.*.inventory.updated` y `warehouse.*.heartbeat` | Worker de proyección del read model. |
| `central.transfer-orchestrator` | `warehouse.events` con `warehouse.*.transfer.*` | Orquestador central de la Saga. |
| `central.audit` | `warehouse.events` con `#` y `central.events` con `#` | Worker de auditoría central. |
| `iot.storage` | `iot.readings` con `iot.#` | Worker de almacenamiento IoT. |
| `iot.alerts` | `iot.readings` con `iot.*.temperature` | Worker de alertas de temperatura. |

## Errores, reintentos y evolución

Un payload inválido, JSON corrupto o una versión de evento no soportada es un error permanente y se envía a la DLQ con un header `x-error`. Errores transitorios (incluidas excepciones no clasificadas) se reintentan mediante `<cola>.retry`, incrementando `x-attempt`; al tercer intento se envían a `<cola>.dlq`. Los detalles operativos y la herramienta de inspección/reproceso corresponden a D-05.

Los consumidores no deben asumir orden global entre colas. Para inventario, `version` es monotónica por fila y permite ignorar eventos viejos. Para IoT, `sequence_number` es monotónica por sensor; lecturas fuera de orden se conservan, pero no reemplazan el último estado. Cambios incompatibles requieren incrementar `event_version` y acordar el despliegue productor/consumidor; campos nuevos opcionales pueden añadirse manteniendo compatibilidad.

## Estado de aprobación

Contrato redactado desde el plan compartido. Requiere revisión y aprobación del equipo para considerarse congelado. La implementación y las pruebas de topología quedan en D-02 y tareas posteriores.
