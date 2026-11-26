# Transacciones distribuidas (F6)

Una transferencia mueve stock entre dos bodegas con bases separadas, así que no
hay una transacción ACID que cubra ambas. Se resuelve con una Saga orquestada: la
central guarda el estado de la transferencia y envía comandos; cada bodega aplica
su paso en una transacción local y responde con un evento. La parte central está
en [ADR-0013](adr/0013-saga-orquestada.md) (E-06); este documento cubre el lado de
la bodega (J-07). El contrato de mensajes está en [events.md](events.md).

## Bodega

### Componentes

| Pieza | Dónde |
| --- | --- |
| Worker de comandos | `services/warehouse-api/workers/commands.py` (`python -m workers.commands`), misma imagen que la API |
| Cola | `wh-00X.commands`, binding `warehouse.commands` con routing key `WH-00X` |
| Migración | `infrastructure/sql/warehouse/migrations/002_saga_commands.sql` |
| Servicios de Compose | `commands-worker` (raíz) y `wh00X_commands` (distribuido) |
| Pruebas | `tests/integration/test_saga_commands.py`, `tests/unit/test_saga_command_parsing.py` |

### Transacción de un comando

Cada mensaje se procesa así, todo dentro de **una** transacción de PostgreSQL:

1. `INSERT INTO processed_messages (message_id, consumer) … ON CONFLICT DO NOTHING`.
   Si no inserta, el `event_id` ya se procesó: se hace ack sin repetir nada.
2. Bloqueo `FOR UPDATE` de la fila de inventario (como en ADR-0004).
3. Cambio de inventario + fila en `inventory_movements` con
   `reference = transfer:<transfer_id>`.
4. Filas de outbox: el evento de respuesta (`warehouse.WH.transfer.<evento>`) y, si
   cambió el inventario, `INVENTORY_UPDATED`.
5. COMMIT. Luego se invalida la caché del SKU y, al retornar el handler,
   `common.rabbit.consume` hace ack.

El relay de outbox (D-03) publica las respuestas después del commit. Si el proceso
muere entre el commit y el ack, RabbitMQ reentrega y el paso 1 lo descarta. Si
muere antes del commit, no queda nada y la reentrega aplica el comando completo.

### Pasos

Cantidades del ejemplo 100/20 → 70/50 (30 unidades de WH-001 a WH-002).

| Comando | Bodega | Efecto en inventario | Movimiento | Respuesta |
| --- | --- | --- | --- | --- |
| `RESERVE_STOCK` | origen | `reserved += q` (100/0 → 100/30) si `now < deadline` y `disponible ≥ q` | `RESERVATION` | `STOCK_RESERVED` o `STOCK_RESERVATION_FAILED` (`DEADLINE_EXCEEDED`, `INSUFFICIENT_STOCK`, `SKU_NOT_FOUND`) |
| `RELEASE_RESERVATION` | origen | `reserved -= q` si la reserva sigue activa | `RESERVATION_RELEASE` | `RESERVATION_RELEASED` (también si no había nada que liberar) |
| `SHIP_TRANSFER` | origen | `quantity -= q`, `reserved -= q` (100/30 → 70/0) | `TRANSFER_OUT` | `TRANSFER_SHIPPED` o `TRANSFER_SHIP_FAILED` (`NO_ACTIVE_RESERVATION`, `SKU_NOT_FOUND`) |
| `RECEIVE_TRANSFER` | destino | `quantity += q` (20 → 50); crea la fila si no existía | `TRANSFER_IN` | `TRANSFER_RECEIVED` o `TRANSFER_RECEIVE_FAILED` (`SKU_NOT_FOUND`, falla permanente) |
| `RETURN_STOCK` | origen | `quantity += q` (70 → 100) si hubo salida; si solo había reserva, la libera | `TRANSFER_RETURN` (o `RESERVATION_RELEASE`) | `STOCK_RETURNED` |

`INVENTORY_UPDATED` acompaña a cada paso que cambia el inventario, con el
`movement_type` del movimiento. Los eventos llevan el `correlation_id` del comando.

### Idempotencia en dos niveles

- **Por mensaje** (`processed_messages`): la misma entrega repetida no hace nada.
- **Por transferencia** (`reference` de los movimientos): si la central reenvía un
  paso con otro `event_id`, la bodega ve que el movimiento ya existe y solo vuelve
  a emitir la respuesta. Así nunca se reserva, despacha o recibe dos veces.

Las decisiones y alternativas están en
[ADR-0020](adr/0020-idempotencia-comandos-bodega.md).

### Casos límite

- `SHIP_TRANSFER` sin reserva activa (nunca existió, ya se liberó o el SKU no existe):
  no mueve inventario y responde `TRANSFER_SHIP_FAILED` con `reason`
  `NO_ACTIVE_RESERVATION` o `SKU_NOT_FOUND`, para que la central compense en vez de
  quedarse esperando en `SOURCE_RESERVED`. E-06 consume el evento,
  pasa a `COMPENSATING` y solicita `RELEASE_RESERVATION`.
  Tras `RESERVATION_RELEASED` termina en `CANCELLED`.
  La integración fue validada con un fallo inducido de envío.
- `RESERVE_STOCK` y el deadline: la hora se toma después de bloquear la fila de
  inventario. Si el comando esperó el `FOR UPDATE` detrás de otra transacción, esa
  espera cuenta contra el deadline.
- Comandos inválidos (sobre mal formado, payload incompleto, `warehouse_id` de otra
  bodega): se loguean `command_invalid` / `command_wrong_warehouse` y se confirman
  para no ciclar. Con D-05 deberán ir a la DLQ.
- Errores de base de datos u otros inesperados: el handler lanza, el mensaje se
  reencola (política actual de `common.rabbit.consume`, que D-05 reemplaza).

### Caos (`CHAOS_FAIL_STEP`)

Solo para pruebas. Valor: lista de `<COMANDO>:<paso>` separada por comas, con paso
`before_commit` o `after_commit`; `*` o solo el paso aplica a todos los comandos.

```bash
CHAOS_FAIL_STEP=SHIP_TRANSFER:after_commit docker compose up -d commands-worker
```

- `before_commit`: rollback completo y reencolado. Con la variable puesta falla
  siempre; al quitarla, el comando se aplica una sola vez.
- `after_commit`: el efecto queda confirmado pero no hay ack; la reentrega se
  detecta como duplicado. Verificado de punta a punta en
  [la evidencia de F6](evidencias/fase-6/saga-bodega-e2e.md).

### Cómo probar

```bash
# Pruebas de integración contra una base de bodega con las migraciones aplicadas
DATABASE_URL=postgresql+psycopg2://admin:admin@localhost:5432/platform pytest tests/integration/test_saga_commands.py
```

La base debe recrearse (`make reset-db`) para que corra la migración 002.
