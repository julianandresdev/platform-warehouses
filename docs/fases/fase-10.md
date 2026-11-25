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

La deduplicación de auditoría no fue verificada.

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

Su validación experimental queda pendiente de D-06.

## Hallazgos y limitaciones

- Redis caído aumenta la latencia.
- Fan-out conserva disponibilidad parcial.
- CQRS requiere sincronización inicial de inventarios.
- Falta confirmar la causa del Fan-out parcial observado
  antes del fallo del 24 de noviembre.
- Las pruebas manuales no sustituyen completamente D-06.

## Estado

- [x] Cinco escenarios manuales ejecutados.
- [x] Evidencias registradas.
- [x] Recuperación de WH-003 verificada.
- [x] Diagnóstico de sincronización de P-001.
- [ ] Validación de scripts oficiales D-06.
- [ ] Matriz de errores y pruebas de retry/DLQ.
- [ ] Validación de consumidor detenido y auditoría.
- [ ] Revisión final.

Las preguntas anteriores son una síntesis técnica
de preparación para la defensa.

[Informe E-07](../load-testing.md).
