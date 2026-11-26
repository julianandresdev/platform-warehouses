# ADR-0015 — Reintentos, DLQ e idempotencia

- Estado: Aceptado.
- Fecha: 26 de noviembre de 2026.
- Responsable: David.

## Contexto

Un error transitorio no debe descartar un mensaje, y un mensaje inválido no debe bloquear una cola mediante reintentos infinitos. La entrega de RabbitMQ es al menos una vez, así que un consumidor también debe tolerar una redelivery después de confirmar su efecto y antes de enviar el ack.

## Alternativas

1. Reencolar inmediatamente con `basic_nack(requeue=True)`: puede crear un ciclo caliente y no limita reintentos.
2. Reintentar indefinidamente en la cola principal: conserva el mensaje, pero puede bloquear mensajes posteriores.
3. Separar retry y DLQ por cola, con expiración y un máximo de intentos.

## Decisión

Usar la tercera alternativa. Cada cola de trabajo `Q` tiene una cola durable `Q.retry` con `x-message-ttl = 5000` y dead-letter routing de vuelta a `Q`, además de una cola durable `Q.dlq`.

El primer procesamiento recibe `x-attempt = 0`. Un error `TransientError` o inesperado programa retry incrementando el header; el tercer procesamiento fallido (recibido con valor `2`) se publica en DLQ. `PermanentError`, JSON corrupto y mensajes que no son un objeto JSON válido pasan directamente a DLQ con `x-error`.

El worker espera publisher confirm antes de confirmar el mensaje original. Si RabbitMQ no confirma la publicación en retry o DLQ, el original se reencola. Los mensajes persistentes conservan body, `message_id` y `correlation_id`. `scripts/dlq.py` permite consultar el tamaño, reproducir mensajes a su cola original o purgarlos.

## Idempotencia

Las operaciones con efectos deben registrar `(event_id, consumer)` en `processed_messages` dentro de la misma transacción del efecto cuando aplique. Los consumidores con idempotencia natural —proyección condicionada por `version`, `DEL` de caché, estado terminal del trabajo de reporte y auditoría con `event_id` único— documentan y mantienen esa garantía.

## Consecuencias

- Los fallos temporales esperan cinco segundos entre intentos y no mantienen ocupado el mensaje original.
- Los mensajes permanentes no hacen reintentos innecesarios.
- Los operadores pueden inspeccionar el conteo, reproducir o purgar una DLQ.
- El procesamiento es al menos una vez; todos los consumidores con efectos deben ser idempotentes.
- Los errores permanentes de negocio deben ser clasificados por el handler con `PermanentError`; las excepciones no clasificadas se tratan como transitorias.


La deduplicación de comandos de Saga se documenta en [ADR-0020](0020-idempotencia-comandos-bodega.md).
