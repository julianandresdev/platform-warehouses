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
