# Evidencia J-07 — Saga de punta a punta (bodega + E-06)

Fecha: 24 nov 2026. Entorno: `compose.distributed.yml` + `compose.central.yml` con
WH-001, WH-002, RabbitMQ 3.13 y la central de la rama `feat/E-06-saga` (PR #56,
todavía sin merge) combinada localmente con esta rama. Seeds de F1: P-001 tiene
100 unidades en WH-001 y 20 en WH-002.

## 1. Caso 100/20 → 70/50

```
POST /transfers  (central, Idempotency-Key: j07-e2e-1, X-Correlation-ID: COR-J07-E2E)
{"source_warehouse_id":"WH-001","destination_warehouse_id":"WH-002","sku":"P-001","quantity":30}
→ 202 {"transfer_id":"ef6839f1-…","status":"PROCESSING"}
```

`GET /transfers/ef6839f1-…` a los ~2 s:

```
status = COMPLETED
REQUESTED → RESERVING_SOURCE → SOURCE_RESERVED → IN_TRANSIT
→ DESTINATION_PENDING → DESTINATION_RECEIVED → COMPLETED
```

| Bodega | Antes | Después | version |
| --- | --- | --- | --- |
| WH-001 `GET /inventory/P-001` | 100 / reservado 0 | **70** / reservado 0 | 3 |
| WH-002 `GET /inventory/P-001` | 20 / reservado 0 | **50** / reservado 0 | 2 |

Conservación: 100 + 20 = 70 + 50. Los tres logs `command_processed` (RESERVE_STOCK,
SHIP_TRANSFER, RECEIVE_TRANSFER) llevan `correlation_id = COR-J07-E2E`.

## 2. Rechazo en destino y compensación

`SOLO-WH1` se creó solo en WH-001 (40 unidades) y se transfirieron 10 a WH-002:

```
status = CANCELLED, reason = SKU_NOT_FOUND
REQUESTED → RESERVING_SOURCE → SOURCE_RESERVED → IN_TRANSIT
→ DESTINATION_PENDING → COMPENSATING → CANCELLED
WH-001 SOLO-WH1: quantity 40, reserved 0 (RESERVATION 10 → TRANSFER_OUT 10 → TRANSFER_RETURN 10)
```

## 3. Caos después del commit

`CHAOS_FAIL_STEP=SHIP_TRANSFER:after_commit` en `wh001_commands`, transferencia de
5 × P-002 (80 en WH-001):

- log `chaos_fail_injected` → `rabbit_handler_failed` (nack, sin ack),
- la reentrega registra `command_duplicate` y se confirma,
- transferencia `COMPLETED`, WH-001 P-002 = **75** (se descontó una sola vez).

## 4. Estado de las bases

WH-001:

```
   sku    |      type       | quantity |                   reference
----------+-----------------+----------+-----------------------------------------------
 P-001    | RESERVATION     |       30 | transfer:ef6839f1-4941-42e3-9deb-24f6b821a6ca
 P-001    | TRANSFER_OUT    |       30 | transfer:ef6839f1-4941-42e3-9deb-24f6b821a6ca
 P-002    | RESERVATION     |        5 | transfer:f177ea9e-4faa-4498-8700-fcf8efe1d096
 P-002    | TRANSFER_OUT    |        5 | transfer:f177ea9e-4faa-4498-8700-fcf8efe1d096
 SOLO-WH1 | RESERVATION     |       10 | transfer:39b2e02f-c306-46af-a72c-da6a4757cea1
 SOLO-WH1 | TRANSFER_OUT    |       10 | transfer:39b2e02f-c306-46af-a72c-da6a4757cea1
 SOLO-WH1 | TRANSFER_RETURN |       10 | transfer:39b2e02f-c306-46af-a72c-da6a4757cea1

    consumer     | count
-----------------+-------
 wh-001.commands |     8

          evento          | count      (outbox publicado)
--------------------------+-------
 INVENTORY_UPDATED        |     8
 STOCK_RESERVATION_FAILED |     1
 STOCK_RESERVED           |     3
 STOCK_RETURNED           |     1
 TRANSFER_SHIPPED         |     3
```

El `STOCK_RESERVATION_FAILED` corresponde a un primer intento con `SOLO-WH1` antes
de que el producto existiera en WH-001 (`reason = SKU_NOT_FOUND`, transferencia
`FAILED`).

WH-002:

```
  sku  |    type     | quantity |                   reference
-------+-------------+----------+-----------------------------------------------
 P-001 | TRANSFER_IN |       30 | transfer:ef6839f1-4941-42e3-9deb-24f6b821a6ca
 P-002 | TRANSFER_IN |        5 | transfer:f177ea9e-4faa-4498-8700-fcf8efe1d096
```

## 5. Pruebas automáticas

`pytest tests` contra PostgreSQL 16 con `schema.sql` + migraciones 001 y 002:
**65 pasadas, 5 omitidas** (las omitidas necesitan RabbitMQ). De ellas, 18 son de
integración de `tests/integration/test_saga_commands.py` (una o más por comando,
duplicados, caos y el caso 100/20 → 70/50) y 19 unitarias de
`tests/unit/test_saga_command_parsing.py`.
