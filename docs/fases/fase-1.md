# Fase 1 — API + PostgreSQL

Líder: Julian · Apoyo: Esteban

## Qué se construyó

- `docker-compose.yaml`: levanta PostgreSQL 16 y la API; la API espera a que la base esté saludable.
- `Dockerfile`: imagen de la API (Python 3.12, uvicorn en el puerto 8000). Una sola imagen para todas las bodegas, configurada por variables de entorno.
- API en FastAPI: CRUD de productos con SKU único, inventario por SKU y movimientos `RECEIPT`, `SHIPMENT` y `ADJUSTMENT`.
- `infrastructure/sql/warehouse/schema.sql`: fuente de verdad del esquema, con las reglas de negocio como restricciones. Se aplica junto con `migrations/` y `seed/<WAREHOUSE_ID>.sql` al crear la base (`init.sh`). Ya no existe `create_all`.
- `WAREHOUSE_ID` (texto, `WH-001`) viene del entorno; el cliente no lo envía.
- Los movimientos se procesan en una transacción con `INSERT ... ON CONFLICT DO NOTHING` y `SELECT ... FOR UPDATE`.
- Autenticación con `X-API-Key` (todo menos `/health` y `/health/ready`).
- `.env.example`: variables de entorno (`DATABASE_URL`, `SQL_ECHO`, `WAREHOUSE_ID`, `API_KEY`).

## Cierre de la fase

- [x] `schema.sql` como fuente de verdad (montado en `/docker-entrypoint-initdb.d/`), sin `create_all`.
- [x] `UNIQUE (product_id, warehouse_id)` en `inventory` e `INSERT ... ON CONFLICT DO NOTHING` antes del bloqueo.
- [x] `CHECK` de cantidades en la base.
- [x] `WAREHOUSE_ID` de tipo texto (`WH-001`) leído del entorno, no del body.
- [x] 409 para stock insuficiente, SKU duplicado y DELETE de un producto con movimientos.
- [x] Tipo de movimiento `ADJUSTMENT` (conteo físico).
- [x] Salidas validadas contra el disponible (`quantity - reserved_quantity`), columna `version`, inventario por SKU, API key y `/health/ready`.
- [x] Pruebas unitarias y de integración automatizadas (incluida la de 2 salidas concurrentes de 6 sobre stock 10): issue E-02 (#32).
- [x] Colección `.http` con las pruebas del README: issue E-02 (#32).

## Decisiones

| Decisión | Elegido | Por qué |
| --- | --- | --- |
| Puerto de la API | 8000 | En macOS el Receptor AirPlay ocupa el 5000 |
| Tipo de `warehouse_id` | Texto (`WH-001`) | Coincide con el enunciado, las llaves de Redis y las routing keys de RabbitMQ |
| Errores de conflicto | 409 Conflict | La solicitud es válida pero choca con el estado actual (stock, SKU, referencias) |
| DELETE de producto con movimientos | 409 Conflict (FK `RESTRICT`) | Más simple que el borrado lógico y no complica el SKU único |
| Fuente del esquema | `schema.sql` | Ver [ADR-0003](../adr/0003-schema-sql-como-fuente-de-verdad.md) |
| Concurrencia | `ON CONFLICT` + `FOR UPDATE` | Ver [ADR-0004](../adr/0004-control-de-concurrencia-en-movimientos.md) |
| Framework | FastAPI | Ver [ADR-0001](../adr/0001-fastapi-como-framework.md) |
| `ADJUSTMENT` | Conteo físico: se envía lo contado y se guarda la diferencia | Refleja lo que hace un inventario real; el historial conserva el cambio, positivo o negativo |

## Preguntas del profesor

### ¿Qué información es estado?

El estado es lo que cambia con las operaciones y de lo que dependen las decisiones: la cantidad en `inventory` (`quantity`, `reserved_quantity` y su `version`). El catálogo de `products` cambia poco; los movimientos son historia.

### ¿Qué información debe persistir?

Todo lo anterior: productos, inventario y movimientos. El inventario puede reconstruirse a partir de los movimientos (auditoría), pero se guarda aparte para leerlo rápido. Debe persistir en PostgreSQL con volumen propio: la API no guarda nada crítico en memoria, así que se puede reiniciar o replicar sin perder datos. Una caché (Fase 2) nunca es la fuente de verdad.

### ¿Por qué una salida necesita una transacción?

Una salida hace dos escrituras que deben ocurrir juntas o ninguna: descontar `inventory.quantity` e insertar el movimiento. Sin transacción, un fallo entre ambas deja stock descontado sin historial (o historial sin descuento). Con la transacción, cualquier error —stock insuficiente, base caída— hace `ROLLBACK` y no queda rastro: ni movimiento, ni cambio de stock, ni la fila de inventario creada para el bloqueo.

### ¿Qué sucede con dos salidas concurrentes?

Con stock 10 y dos salidas simultáneas de 6, el `SELECT ... FOR UPDATE` bloquea la fila de inventario: la segunda transacción espera, lee el stock ya actualizado (4) y se rechaza con 409. Resultado: un 201, un 409 y stock final 4. Para la primera entrada de un producto (sin fila que bloquear), `INSERT ... ON CONFLICT DO NOTHING` sobre `UNIQUE (product_id, warehouse_id)` evita que dos peticiones creen dos filas. Detalle en [ADR-0004](../adr/0004-control-de-concurrencia-en-movimientos.md).

## Evidencia

Verificación manual del cierre (PostgreSQL 18 local, API real, sin mocks):

- 20 rondas de 2 salidas simultáneas de 6 sobre stock 10: en las 20, un 201, un 409 y stock final 4.
- 20 rondas de 4 primeras entradas simultáneas de 5 unidades: en las 20, una sola fila de inventario, cantidad 20 y `version` 4.
- Salida mayor al stock: 409 y el conteo de movimientos no cambia.
- `CHECK` y `UNIQUE` rechazan escrituras directas en la base que violan las reglas.

### E-02 (#32) — Pruebas automatizadas

Las pruebas se ejecutaron contra PostgreSQL 16 real,
en una base aislada llamada `platform_test`.

| Grupo de pruebas | Aprobadas |
| --- | ---: |
| Unitarias existentes | 28 |
| Validacion de schemas | 17 |
| Calculo de ADJUSTMENT | 7 |
| Entorno PostgreSQL | 3 |
| Integracion de productos | 4 |
| Integracion de inventario | 5 |
| Concurrencia | 2 |
| **Total** | **66** |

Comando de ejecucion:

```bash
python -m pytest tests/unit tests/integration/fase1 -q
```

Resultado: 66 pruebas aprobadas.

Los fixtures utilizan `TRUNCATE ... RESTART IDENTITY CASCADE`
antes y despues de cada prueba, con una proteccion que
restringe la limpieza a la base de pruebas autorizada.

#### Concurrencia

Se ejecutaron 20 rondas de ambos escenarios:

- Dos salidas simultaneas de 6 unidades sobre stock 10:
  HTTP 201 y 409, stock final 4 y version 2.
- Cuatro primeras entradas simultaneas de 5 unidades:
  cuatro respuestas 201, una sola fila de inventario,
  stock final 20 y version 4.

#### Coleccion HTTP

Archivo: [fase-1.http](../../tests/http/fase-1.http).

Se implementaron los 12 escenarios del README y se
verificaron sus 18 solicitudes equivalentes mediante HTTPX
contra una instancia real de FastAPI.

#### Evidencia PostgreSQL

SKU utilizado: `E02-HTTP-1795494981`.

Estado final:

| SKU | Bodega | Cantidad | Reservado | Version |
| --- | --- | ---: | ---: | ---: |
| E02-HTTP-1795494981 | WH-001 | 5 | 0 | 3 |

Historial persistido:

| Tipo | Cantidad |
| --- | ---: |
| RECEIPT | 10 |
| SHIPMENT | 4 |
| ADJUSTMENT | -1 |

La salida rechazada de 15 unidades retorno HTTP 409
y no modifico el inventario ni genero un movimiento.

Eventos persistidos en Outbox: 3.

#### Integracion continua

El workflow `.github/workflows/fase-1-tests.yml`
automatiza las pruebas unitarias y de integracion
utilizando un servicio PostgreSQL 16 independiente.

La ejecucion remota se verifica en GitHub Actions.


## J-03 — `services/common`: sobre de eventos, correlation ID y logs JSON

- `common/events.py`: `EventEnvelope` (Pydantic) y `new_event()` según `docs/events.md`; `occurred_at` en UTC con `Z` y sin fracciones.
- `common/correlation.py`: `ContextVar` + `CorrelationIdMiddleware` (ASGI puro). Lee `X-Correlation-ID` o genera `COR-YYYYMMDD-<8 hex>` y lo devuelve en la respuesta.
- `common/logging.py`: logs JSON por stdout (`timestamp`, `service`, `warehouse_id`, `level`, `event`, `correlation_id` + extras), sin dependencias externas. Nivel con `LOG_LEVEL`.
- `common/errors.py`: `TransientError` y `PermanentError` para los consumidores (F10).
- La Warehouse API registra una línea `request` por llamada (método, ruta, status, `duration_ms`) y desactiva el access log de uvicorn.
- Pruebas: `pip install -r requirements-dev.txt && pytest tests/unit`.

Ejemplo (request con `X-Correlation-ID: COR-TEST`):

```json
{"timestamp": "2026-11-22T23:09:23.395Z", "service": "warehouse-api", "warehouse_id": "WH-001", "level": "INFO", "event": "request", "correlation_id": "COR-TEST", "method": "GET", "path": "/health", "status": 200, "duration_ms": 1.69}
```
