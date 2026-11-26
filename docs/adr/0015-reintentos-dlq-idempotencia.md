# ADR-0015 — Reintentos, DLQ e idempotencia

## Estado

Propuesto según el plan. David debe validar la implementación y las pruebas de D-05.

## Contexto y alternativas

Reencolar indefinidamente mantiene disponible el mensaje, pero un fallo permanente ocupa al consumidor sin progreso. Descartarlo pierde información útil para diagnóstico. Una política acotada permite dar tiempo a los fallos transitorios y separar los mensajes que requieren intervención.

## Decisión

Usar una cola de reintento por consumidor con TTL de cinco segundos y retorno a la cola original. Incrementar `x-attempt` y derivar a DLQ al agotar tres intentos. Los errores permanentes van directamente a DLQ con `x-error`. Confirmar el original después de publicar el reemplazo. Para efectos persistentes, registrar el identificador del mensaje junto con el cambio de negocio o justificar la idempotencia con la versión de la proyección o con la operación aplicada.

## Consecuencias y validación

Los mensajes pueden entregarse más de una vez. La DLQ permite inspección y reproducción controlada. La rama actual todavía reencola excepciones en el [consumidor compartido](../../services/common/common/rabbit.py). Ver la [deduplicación de comandos Saga](0020-idempotencia-comandos-bodega.md). Quedan por comprobar un JSON inválido y un error transitorio que agota los reintentos, según el [issue D-05](https://github.com/julianandresdev/platform-warehouses/issues/19).
