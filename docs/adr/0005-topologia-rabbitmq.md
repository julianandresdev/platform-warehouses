# ADR-0005: Topología de RabbitMQ y entrega confirmada

- Estado: Aceptado como decisión del plan; implementación inicial en D-02.
- Fecha: 22 de noviembre de 2026.
- Autor: David.

## Contexto

Los servicios necesitan enviar eventos y comandos entre bodegas, la central e IoT. La mensajería debe sobrevivir reinicios del broker, confirmar publicaciones y permitir consumidores independientes. El contrato acordado está en [events.md](../events.md).

## Alternativas

1. Usar RabbitMQ con exchanges por dominio y colas durables por consumidor.
2. Usar una cola única y filtrar mensajes dentro de cada consumidor.
3. Usar un broker distinto o llamadas HTTP síncronas entre servicios.

## Decisión

Usar RabbitMQ con `warehouse.events` y `central.events` como exchanges `topic`, `warehouse.commands` como `direct`, `iot.readings` como `topic` y `dlx` como exchange `direct`. Las colas son durables y se enlazan con routing keys específicas por bodega y consumidor. El código compartido declara la topología de forma idempotente. Las publicaciones llevan mensajes persistentes y esperan publisher confirms; el relay del outbox se implementa en D-03 para que las operaciones de inventario no dependan de la disponibilidad inmediata del broker.

## Consecuencias

- Cada consumidor puede escalar de forma independiente y recibe solo los mensajes de sus bindings.
- RabbitMQ puede acumular mensajes mientras un worker está detenido.
- La entrega es al menos una vez; cada consumidor debe ser idempotente.
- La topología y el broker añaden operación local. Los reintentos y las DLQ se completarán en D-05.
- En D-02, errores del handler se reencolan; la clasificación y el flujo de retry/DLQ se incorporarán en D-05.
