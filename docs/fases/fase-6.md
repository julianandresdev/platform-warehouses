# Fase 6 — Transferencias con Saga

## J-07 — Lado bodega: consumidor de comandos

### Qué se hizo

- Worker `workers.commands` en la imagen de bodega, consumiendo `wh-00X.commands`
  (servicio `commands-worker` en el Compose raíz y `wh00X_commands` en el distribuido).
- Migración `002_saga_commands.sql`: tabla `processed_messages(message_id, consumer,
  processed_at)` con PK compuesta y cinco tipos de movimiento de transferencia.
- `RESERVE_STOCK` (respeta `deadline` y disponible), `RELEASE_RESERVATION`,
  `SHIP_TRANSFER`, `RECEIVE_TRANSFER` (falla permanente si el SKU no existe) y
  `RETURN_STOCK`.
- Cada comando: una transacción con `processed_messages` + inventario + movimiento +
  outbox (respuesta e `INVENTORY_UPDATED`); ack después del commit.
- `CHAOS_FAIL_STEP` para fallar antes o después del commit.
- Documentación: sección Bodega de [distributed-transactions.md](../distributed-transactions.md)
  y [ADR-0020](../adr/0020-idempotencia-comandos-bodega.md).

### Evidencia

[evidencias/fase-6/saga-bodega-e2e.md](../evidencias/fase-6/saga-bodega-e2e.md):

- Con la central de E-06, P-001 pasa de 100/20 a **70/50** y la transferencia
  termina `COMPLETED` en ~2 s.
- SKU inexistente en destino → `TRANSFER_RECEIVE_FAILED` → `RETURN_STOCK` →
  `CANCELLED`, y el origen vuelve a su stock inicial.
- `CHAOS_FAIL_STEP=SHIP_TRANSFER:after_commit`: la reentrega se detecta como
  duplicado y el stock se descuenta una sola vez.
- `pytest tests`: 65 pasadas, 5 omitidas (requieren RabbitMQ).

### Preguntas del profesor

**¿Qué pasa si la bodega procesa un comando y se cae antes del ack?**
El efecto y la fila de `processed_messages` ya están confirmados. RabbitMQ reentrega
el mensaje; el `INSERT … ON CONFLICT DO NOTHING` no inserta y el worker hace ack sin
repetir nada. Las respuestas ya están en el outbox, así que también se publican.

**¿Y si se cae antes del commit?**
La transacción se revierte entera (no queda reserva, movimiento, evento ni registro
del mensaje). La reentrega procesa el comando como si fuera la primera vez.

**¿Por qué la reserva no descuenta `quantity`?**
Porque el stock sigue físicamente en la bodega hasta el envío. La reserva solo baja el
disponible (`quantity - reserved_quantity`), que es lo que validan las salidas
normales; así una venta local no puede llevarse unidades comprometidas.

**¿Cómo se evita aplicar dos veces un paso que la central reenvía con otro `event_id`?**
Los movimientos guardan `reference = transfer:<id>`. Con la fila de inventario
bloqueada, el worker revisa si el paso ya existe para esa transferencia; si es así,
solo vuelve a emitir la respuesta (ADR-0020).

### Pendiente

- La central (E-06, #56) debe consumir `TRANSFER_SHIP_FAILED` (nuevo en `docs/events.md`)
  y pasar de `SOURCE_RESERVED` a compensación. La bodega ya lo emite para
  `SHIP_TRANSFER` sin reserva activa; falta acordar el nombre y la transición con Esteban.
- Reintentos con límite y DLQ para comandos inválidos o con error: D-05.
