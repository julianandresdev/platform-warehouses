# Fase 6 — Transferencias distribuidas mediante Saga


## E-06: Orquestador central de Saga

### Objetivo

Coordinar transferencias de inventario entre bodegas
independientes mediante una Saga orquestada desde
la plataforma central, sin utilizar una transaccion
distribuida global.

### Componentes implementados

- Maquina de estados de transferencias.
- Persistencia de transferencias e historial en PostgreSQL.
- Central API para solicitar y consultar transferencias.
- Outbox Relay para publicar comandos y eventos.
- Orquestador consumidor de eventos RabbitMQ.
- Temporizador para detectar transferencias vencidas.
- Control de idempotencia mediante processed_messages.
- Logs estructurados y propagacion de correlation ID.

### Endpoints

- POST /transfers
- GET /transfers/{transfer_id}

La creacion de transferencias utiliza Idempotency-Key
para evitar solicitudes duplicadas.

### Flujo exitoso

REQUESTED -> RESERVING_SOURCE -> SOURCE_RESERVED
-> IN_TRANSIT -> DESTINATION_PENDING
-> DESTINATION_RECEIVED -> COMPLETED.

### Manejo de fallos

- Reserva rechazada: estado FAILED.
- Recepcion rechazada: estado COMPENSATING, seguido
  de CANCELLED tras confirmar RETURN_STOCK.
- Reserva sin respuesta durante 30 segundos: FAILED.
- Reserva confirmada fuera del plazo:
  comando RELEASE_RESERVATION.
- Destino sin respuesta durante cinco minutos:
  alerta en logs sin cancelar la transferencia.
- Reinicio del orquestador: recuperacion mediante
  PostgreSQL y mensajes pendientes en RabbitMQ.

### Garantias de consistencia

- Persistencia atomica de estados, historial y Outbox.
- Bloqueo de filas para controlar modificaciones concurrentes.
- Deduplicacion de eventos mediante event_id y consumer.
- Rechazo de transiciones incompatibles.
- Publicacion asincrona de comandos.
- Conservacion del estado ante reinicios.

### Pruebas realizadas

| Escenario | Resultado |
| --- | --- |
| Creacion y consulta de transferencias | Exitoso |
| Idempotencia de solicitudes HTTP | Exitoso |
| Publicacion mediante Outbox | Exitoso |
| Transferencia exitosa simulada | Exitoso |
| Eventos duplicados | Exitoso |
| Eventos incompatibles | Exitoso |
| Reserva rechazada | Exitoso |
| Recepcion rechazada y compensacion | Exitoso |
| Timeout real de reserva | Exitoso |
| Reserva tardia y liberacion | Exitoso |
| Recuperacion tras reiniciar el worker | Exitoso |
| Destino no disponible simulado | Exitoso |
| Alerta de cinco minutos con fecha simulada | Exitoso |
| Pruebas unitarias pytest | 36/36 |

### Limitaciones y pendientes

Las pruebas funcionales utilizaron bodegas simuladas,
PostgreSQL y RabbitMQ reales en Docker.

La alerta de destino pendiente se verifico modificando
la antiguedad de una transferencia de prueba.

La deduplicacion de alertas se mantiene en memoria
durante cada ejecucion del worker. Un reinicio puede
generar nuevamente una alerta para una transferencia
que siga pendiente.

La integracion con J-07 queda pendiente para verificar
el movimiento real de inventario, las compensaciones
fisicas y el invariante de conservacion de stock.

Tambien queda pendiente acordar el tratamiento del
fallo definitivo de envio con el equipo.

### Decision arquitectonica

Consultar ADR-0013: Saga orquestada desde la central.
