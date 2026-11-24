# ADR-0013 — Saga orquestada desde la plataforma central

## Estado

Aceptado para la implementacion de E-06.
Integracion con J-07 pendiente.

## Contexto

La plataforma administra multiples bodegas independientes,
cada una con su propia base de datos PostgreSQL.

Una transferencia de inventario requiere coordinar
operaciones de reserva, envio y recepcion entre servicios
sin disponer de una transaccion ACID global.

Los fallos parciales pueden dejar una transferencia
incompleta y requieren mecanismos de recuperacion
y compensacion.

## Alternativas consideradas

### Saga coreografiada

Cada servicio reacciona a eventos y determina
la siguiente operacion del proceso.

Ventajas:

- Menor dependencia de un coordinador central.
- Distribucion de la logica entre servicios.

Desventajas:

- Mayor dificultad para rastrear transferencias.
- Logica de compensacion distribuida.
- Mayor complejidad para administrar estados y timeouts.

### Saga orquestada

Un coordinador central administra el estado de cada
transferencia y publica los comandos correspondientes.

Ventajas:

- Flujo de estados explicito.
- Historial centralizado.
- Control de compensaciones y timeouts.
- Mayor facilidad de observabilidad y recuperacion.

Desventajas:

- Dependencia del orquestador para avanzar transferencias.
- Mayor responsabilidad de la plataforma central.
- Necesidad de persistir el estado de la coordinacion.

## Decision

Implementar una Saga orquestada desde la plataforma
central utilizando:

- PostgreSQL para persistir estados e historial.
- RabbitMQ para intercambiar comandos y eventos.
- Transactional Outbox para persistir mensajes junto
  con los cambios de estado.
- Idempotency-Key para deduplicar solicitudes HTTP.
- processed_messages para deduplicar eventos.
- Bloqueos de filas para controlar concurrencia.
- Acciones compensatorias ante fallos confirmados.
- Correlation ID para trazabilidad.

La central coordina las operaciones, pero cada bodega
conserva la responsabilidad sobre su inventario local.

## Manejo de fallos

Una reserva sin respuesta durante 30 segundos produce
el estado FAILED.

Una confirmacion de reserva tardia genera un comando
RELEASE_RESERVATION.

Un rechazo de recepcion genera un comando RETURN_STOCK
y la transferencia pasa a CANCELLED cuando se confirma
la compensacion.

Si el destino permanece pendiente durante cinco minutos,
se registra una alerta sin cancelar la transferencia.

El estado persistido permite recuperar la coordinacion
tras reiniciar el orquestador.

## Consecuencias

Positivas:

- Coordinacion explicita y trazable.
- Recuperacion de transferencias pendientes.
- Procesamiento asincrono.
- Control de eventos duplicados.
- Independencia de las bases de datos de las bodegas.

Negativas:

- Consistencia eventual entre servicios.
- Mayor complejidad respecto a una transaccion local.
- Posibilidad de publicaciones duplicadas por Outbox.
- Dependencia de consumidores idempotentes.
- Necesidad de monitorear transferencias pendientes.

## Validacion

La implementacion central fue validada mediante
36 pruebas unitarias y pruebas funcionales simuladas
con PostgreSQL y RabbitMQ.

La integracion real con J-07 y la verificacion del
invariante de conservacion de inventario quedan pendientes.

La solucion no garantiza una transaccion ACID global
ni entrega exactamente una vez de los mensajes.
