# Fase 3 — RabbitMQ y workers

## Avance D-02 — Conexión y topología

Se añadió RabbitMQ con consola de management y healthcheck a los Compose raíz y distribuido. El paquete `services/common` incluye el cliente `common.rabbit` para conexión con reintento, declaración durable e idempotente de exchanges, colas y bindings, publicación JSON persistente con publisher confirms y consumo con ack manual. El consumidor establece el `correlation_id` en el ContextVar compartido mientras ejecuta el handler y confirma el mensaje solo si el handler retorna correctamente.

Los errores del handler se reencolan por ahora. El límite de reintentos y las DLQ pertenecen a D-05. El ContextVar queda expuesto para que J-03 integre después el middleware HTTP con el mismo contexto.

## Contrato

La topología y los mensajes están documentados en [events.md](../events.md). La decisión de exchanges y entrega está en [ADR-0005](../adr/0005-topologia-rabbitmq.md).

## Evidencia y preguntas

La prueba `tests/integration/test_rabbit.py` publica y consume un mensaje real y comprueba el correlation ID dentro del handler. Para ejecutarla con el broker disponible: `RABBITMQ_URL=amqp://guest:guest@localhost:5672/%2F pytest -q tests/integration/test_rabbit.py`.

Pendiente guardar evidencia visual de la consola de management y ejecutar la prueba contra un broker; Docker Engine no estaba disponible durante esta implementación. Las preguntas del profesor de F3 se completarán al integrar D-03 y D-04.
