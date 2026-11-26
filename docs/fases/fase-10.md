# Fase 10 — Resiliencia

## Objetivo

Evaluar el comportamiento de la plataforma ante fallos
de sus componentes y verificar la recuperación.

## Pruebas manuales

| Escenario | Resultado |
|---|---|
| Redis detenido | HTTP 200 mediante BYPASS |
| RabbitMQ detenido | Movimiento persistido y evento publicado al recuperar |
| Worker detenido | Evento pendiente y publicado al reiniciar |
| Evento duplicado | Proyección de inventario sin cambios |
| Bodega inaccesible | Respuesta parcial y recuperación verificada |

## Preguntas de análisis y defensa

### ¿Qué ocurre si Redis deja de funcionar?

La API consulta PostgreSQL mediante Cache Aside.
Se conserva la disponibilidad, aunque aumenta la latencia.

[Evidencia](../evidencias/fase-10/redis-durante-1.txt).

### ¿Qué ocurre si RabbitMQ deja de funcionar?

El movimiento y el evento se almacenan en PostgreSQL.
El relay publica el evento cuando RabbitMQ vuelve.

[Evidencia pendiente](../evidencias/fase-10/rabbitmq-outbox-pendiente.txt).
[Evidencia de publicación](../evidencias/fase-10/rabbitmq-outbox-publicado.txt).

### ¿Cómo se recupera un worker detenido?

Los eventos pendientes permanecen en outbox.
Al reiniciar el relay se reanuda su publicación.

[Evidencia](../evidencias/fase-10/worker-outbox-publicado.txt).

### ¿Cómo se evita modificar el inventario por duplicados?

La proyección utiliza versiones del inventario para
evitar que eventos iguales o antiguos sobrescriban
el estado actualizado.

[Evidencia](../evidencias/fase-10/duplicado-resultado.txt).

El [caso 4 de D-06](../evidencias/fase-10/caso-4.txt) verificó que la auditoría
inserta una sola fila aunque RabbitMQ entregue dos veces el mismo `event_id`.

### ¿Qué ocurre si una bodega deja de responder?

Fan-out entrega los resultados disponibles e identifica
la bodega inaccesible. Al recuperarla, vuelve a incluirla.

[Fallo](../evidencias/fase-10/fanout-durante-1.txt).
[Recuperación](../evidencias/fase-10/fanout-despues-1.txt).

### ¿Cuándo se utilizan reintentos y DLQ?

Los errores transitorios pueden reintentarse.
Los errores permanentes o los mensajes que agotan
sus reintentos deben enviarse a una Dead Letter Queue
para su inspección y tratamiento.

D-05 implementa la cola `.retry` con TTL de cinco segundos, el límite de tres intentos, el envío directo de errores permanentes a `.dlq` y el CLI para inspección, reproducción y purga. Las pruebas automatizadas de RabbitMQ cubren JSON corrupto, error permanente y agotamiento de reintentos. D-06 conserva la validación manual de escenarios y evidencias oficiales.

## Hallazgos y limitaciones

- Redis caído aumenta la latencia.
- Fan-out conserva disponibilidad parcial.
- CQRS requiere sincronización inicial de inventarios.
- Falta confirmar la causa del Fan-out parcial observado
  antes del fallo del 24 de noviembre.
- Las pruebas manuales no sustituyen completamente D-06.

## Matriz de errores para revisión

La matriz combina los cuatro casos de manejo de mensajes y consumidores
con los cuatro fallos operativos adicionales de D-06. Los scripts de
`tests/chaos/` ejecutan los escenarios reproducibles y guardan su salida
en `docs/evidencias/fase-10/`.

| Fallo | Respuesta y recuperación | Justificación y evidencia |
| --- | --- | --- |
| Fallo transitorio al procesar un mensaje | Publicar en `<cola>.retry` con espera de cinco segundos; tras el tercer fallo, enviar a DLQ. | Evita ciclos de requeue sin límite. Prueba automatizada: `test_transient_error_is_retried_three_times_then_dead_lettered` de D-05. |
| Sobre, JSON o versión inválida | Enviar directamente a DLQ con diagnóstico `x-error`; no reintentar una entrada que no puede corregirse sola. | Prueba automatizada: `test_invalid_json_goes_directly_to_dlq` de D-05. |
| Entrega duplicada | Deduplicar por `event_id`; la proyección registra `(message_id, consumer)` en la transacción y auditoría usa clave primaria. | [Caso 4](../evidencias/fase-10/caso-4.txt): doble publicación del mismo heartbeat, un efecto en cada consumidor. |
| Consumidor detenido | Mantener el mensaje en la cola durable hasta que el consumidor vuelva. | [Caso 3](../evidencias/fase-10/caso-3.txt): mensaje visible en `central.projection` y versión aplicada después de recuperar el worker. |
| RabbitMQ no disponible al publicar | Confirmar el movimiento y el evento en PostgreSQL. El relay publica cuando vuelve el broker. | [Caso 2](../evidencias/fase-10/caso-2.txt): una fila pendiente pasa a publicada tras recuperar el broker. Evidencia previa: [pendiente](../evidencias/fase-10/rabbitmq-outbox-pendiente.txt) · [publicada](../evidencias/fase-10/rabbitmq-outbox-publicado.txt). |
| Destino de la Saga inaccesible | Mantener `DESTINATION_PENDING` después del envío. Completar cuando vuelva el consumidor o compensar si el destino devuelve un rechazo definitivo. | Cancelar ante un silencio puede duplicar unidades en tránsito. [Historial de la transferencia](../evidencias/fase-11/traza-transferencia-saga.json) |
| Versión de evento desconocida | El plan la clasifica como error permanente y deriva el mensaje a DLQ con un diagnóstico. | Repetir el mismo mensaje no vuelve compatible su contrato. D-05 lo envía directamente a DLQ; cubierto por clasificación de errores permanentes. |
| Redis no disponible | Leer PostgreSQL y responder con `X-Cache: BYPASS`. Recuperar el uso de caché cuando Redis vuelve. | PostgreSQL conserva la fuente de verdad. [Caso 1](../evidencias/fase-10/caso-1.txt): HTTP 200 y BYPASS durante la caída. |
| API y relay de una bodega inaccesibles | La central sigue respondiendo y marca `stale=true` después de 90 segundos sin heartbeat; el estado se normaliza al recuperar la bodega. | [Caso 5](../evidencias/fase-10/caso-5.txt): caída y recuperación de WH-003. |

## Estado

- [x] Cinco escenarios automatizados de D-06 ejecutados.
- [x] Evidencias registradas en `docs/evidencias/fase-10/caso-*.txt`.
- [x] Recuperación de WH-003 verificada.
- [x] Diagnóstico de sincronización de P-001.
- [x] Cinco scripts de caos de D-06 ejecutados con salida guardada.
- [x] Pruebas automatizadas de retry/DLQ de D-05; la matriz manual completa queda para D-06.
- [x] Recuperación de consumidor y deduplicación de auditoría verificadas.
- [ ] Revisión final.

Las preguntas anteriores son una síntesis técnica
de preparación para la defensa.

[Informe E-07](../load-testing.md).
