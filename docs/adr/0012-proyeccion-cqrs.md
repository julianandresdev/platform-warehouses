# ADR-0012: Proyección CQRS del inventario global

- Estado: Aceptado.
- Fecha: 23 de noviembre de 2026.
- Responsable: Esteban.

## Contexto
La plataforma necesita consultar inventario consolidado sin depender
de la disponibilidad inmediata de todas las bodegas.

## Alternativas
1. Consultar cada bodega durante cada petición (fanout).
2. Mantener una proyección central actualizada mediante eventos.

## Decisión
Utilizar CQRS con RabbitMQ y PostgreSQL central.
El worker consume central.projection y actualiza global_inventory.
Las versiones antiguas no sobrescriben versiones nuevas.
processed_messages evita procesar dos veces el mismo event_id.
Los heartbeats actualizan warehouse_status.

Las consultas globales utilizan exclusivamente PostgreSQL central.
Una bodega se marca stale si no registra heartbeat en más de 90 s.

## Observabilidad
El worker expone /metrics en el puerto interno 9101.
projection_lag_seconds mide los segundos transcurridos entre
occurred_at y el procesamiento exitoso del último evento.
La métrica se reinicia cuando se reinicia el worker.

## Consecuencias
- Las consultas no dependen de que todas las bodegas estén disponibles.
- Se acepta consistencia eventual.
- Los datos de bodegas sin heartbeat pueden estar desactualizados.
- Los eventos duplicados o desordenados no deben corromper la proyección.
