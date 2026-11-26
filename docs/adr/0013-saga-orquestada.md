# ADR-0013 — Saga orquestada desde la plataforma central

## Estado

Aceptado para la implementacion de E-06.
Integracion con J-07 validada localmente. PR #56 pendiente de fusion.

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

Un fallo definitivo de envio (TRANSFER_SHIP_FAILED)
desde SOURCE_RESERVED genera RELEASE_RESERVATION.
La transferencia pasa a COMPENSATING y termina en
CANCELLED al recibir RESERVATION_RELEASED.

No se utiliza RETURN_STOCK porque la mercancia no
ha salido de la bodega.

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

Posteriormente se ampliaron las pruebas unitarias a 46/46
y se validaron cinco escenarios de integracion con J-07.

Se comprobo la conservacion de inventario, idempotencia
HTTP, rechazo por stock insuficiente y compensaciones
por fallos de recepcion y envio.

Ver [evidencias E-06](../evidencias/fase-6/e06-integracion.md).

La solucion no garantiza una transaccion ACID global
ni entrega exactamente una vez de los mensajes.
