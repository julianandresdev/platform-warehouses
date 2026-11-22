# Warehouse Cloud Platform

Backend de la primera fase de Warehouse Cloud Platform.

En este Sprint se implementó una API REST con FastAPI y PostgreSQL para administrar productos e inventario de una bodega.

## Tecnologías

- Python 3.12
- FastAPI
- SQLAlchemy
- PostgreSQL 16
- psycopg2
- Docker
- Docker Compose

## Funcionalidades implementadas

### Productos

Se implementó el CRUD completo de productos:

- Crear un producto.
- Listar productos.
- Consultar un producto por ID.
- Actualizar un producto.
- Eliminar un producto.
- Validar que el SKU sea único.

Endpoints:

- `POST /products`
- `GET /products`
- `GET /products/{product_id}`
- `PUT /products/{product_id}`
- `DELETE /products/{product_id}`

### Inventario

El inventario es el de **una bodega**, la que define la variable de entorno `WAREHOUSE_ID` (texto, p. ej. `WH-001`). El cliente nunca envía el identificador de la bodega. Los productos se identifican por **SKU**.

Endpoints:

- `GET /inventory/{sku}`: cantidad, reservada, disponible y versión.
- `POST /inventory/movements`: registra un movimiento (`sku`, `type`, `quantity`, `reference`).
- `GET /inventory/{sku}/movements`: historial, del más reciente al más antiguo.

Los movimientos permitidos son:

- `RECEIPT`: entrada de unidades (`quantity` > 0).
- `SHIPMENT`: salida de unidades (`quantity` > 0). Se valida contra lo **disponible** (`quantity - reserved_quantity`).
- `ADJUSTMENT`: conteo físico. Se envía la cantidad contada (`quantity` >= 0) y el movimiento guarda la **diferencia** contra el inventario (puede ser negativa). El conteo no puede quedar por debajo de lo reservado ni coincidir con el inventario actual.

Cada cambio del inventario sube `version` en 1.

### Seguridad

Todos los endpoints, salvo `/health` y `/health/ready`, exigen el header `X-API-Key` con el valor de la variable `API_KEY`. Sin la clave, o con una incorrecta, la API responde 401. La API no arranca si `API_KEY` no está configurada.

- `GET /health`: la API está viva.
- `GET /health/ready`: la API puede hablar con PostgreSQL (503 si no).

### Códigos de error

| Situación | Código |
| --- | --- |
| Producto o inventario inexistente | 404 |
| SKU duplicado | 409 |
| Stock insuficiente en una salida | 409 |
| Conteo (`ADJUSTMENT`) bajo lo reservado o sin diferencia | 409 |
| Borrar un producto con inventario o movimientos | 409 |
| Cuerpo inválido (p. ej. `quantity` <= 0 en una entrada) | 422 |
| Falta o es incorrecta la API key | 401 |

Se usa 409 Conflict porque la solicitud es válida pero choca con el estado actual.

### Control de stock y concurrencia

Los movimientos de inventario se procesan en una sola transacción:

1. Se garantiza que exista la fila de inventario con `INSERT ... ON CONFLICT (product_id, warehouse_id) DO NOTHING`.
2. Se bloquea esa fila con `SELECT ... FOR UPDATE`.
3. Se valida la regla del movimiento (stock disponible, conteo).
4. Se actualiza `quantity` y `version`, y se registra el movimiento.
5. Se confirma la transacción.

Si cualquier validación falla, la transacción se revierte completa: no queda movimiento, ni cambio de stock, ni fila de inventario creada solo para el bloqueo. Dos salidas simultáneas de 6 unidades sobre un stock de 10 dan exactamente un 201 y un 409.

Además, la base impone sus propias reglas (`UNIQUE (product_id, warehouse_id)`, `quantity >= 0`, `reserved_quantity` entre 0 y `quantity`, movimientos con `quantity <> 0`) como última línea de defensa. Ver `infrastructure/sql/warehouse/schema.sql`.

## Estructura principal

```text
platform-warehouses/
├── docker-compose.yaml
├── Makefile
├── .env.example
├── docs/
│   ├── adr/          # decisiones de arquitectura
│   └── fases/        # avance y respuestas por fase
├── infrastructure/
│   ├── compose/      # compose por escenario (bodegas distribuidas, batch)
│   └── sql/warehouse/
│       ├── schema.sql      # fuente de verdad del esquema
│       ├── migrations/     # cambios posteriores: NNN_descripcion.sql
│       ├── seed/           # WH-001.sql, WH-002.sql, WH-003.sql
│       └── init.sh         # aplica lo anterior al crear la base
├── services/
│   └── warehouse-api/
│       ├── Dockerfile
│       ├── app.py
│       ├── config.py
│       ├── database.py
│       ├── models.py
│       ├── schemas.py
│       ├── services.py
│       └── requirements.txt
└── tests/load/       # Locust
```

### Archivos principales

`app.py`

Contiene la aplicación FastAPI, la validación de la API key y los endpoints HTTP.

`config.py`

Lee `WAREHOUSE_ID` y `API_KEY` del entorno.

`database.py`

Configura SQLAlchemy, la conexión con PostgreSQL y las sesiones. **No crea tablas**: el esquema lo aplica PostgreSQL desde `schema.sql`.

`models.py`

Contiene los modelos SQLAlchemy (Product, Inventory, InventoryMovement). Reflejan `schema.sql`; si cambia una tabla se cambia primero el SQL.

`schemas.py`

Contiene los modelos Pydantic utilizados para validar las solicitudes y respuestas de la API.

`services.py`

Contiene la lógica de negocio: CRUD de productos, consulta de inventario, historial y procesamiento transaccional de movimientos.

### Esquema de la base de datos

`schema.sql` es la única fuente del esquema. PostgreSQL lo ejecuta, junto con `migrations/*.sql` y `seed/<WAREHOUSE_ID>.sql`, **solo cuando el volumen de datos está vacío** (`init.sh`). Para aplicar un cambio en esos archivos hay que recrear la base con `make reset-db` (borra los datos locales). Los cambios posteriores al esquema inicial van como `migrations/NNN_descripcion.sql`.

La semilla carga el mismo catálogo de 10 productos (`P-001` a `P-010`) en cada bodega, con stock distinto (por ejemplo `P-001`: 100 en WH-001, 20 en WH-002).

## Ejecución

Desde la raíz del proyecto ejecutar:

```bash
docker compose up --build
```

Docker Compose inicia:

- PostgreSQL en el puerto 5432, con el esquema y la semilla de `WH-001` ya aplicados.
- FastAPI en el puerto 8000.

Variables de entorno (ver `.env.example`): `WAREHOUSE_ID` (por defecto `WH-001`) y `API_KEY` (por defecto `dev-api-key` en desarrollo).

> Se usa 8000 y no 5000 porque en macOS el Receptor AirPlay ocupa el puerto 5000 y la API queda inaccesible sin un error claro.

El servicio de la API espera a que PostgreSQL esté saludable antes de iniciar.

La API queda disponible en:

```text
http://localhost:8000
```

La documentación interactiva de FastAPI está disponible en:

```text
http://localhost:8000/docs
```

## Pruebas

Los ejemplos usan la clave de desarrollo. Para no repetirla:

```bash
export KEY='X-API-Key: dev-api-key'
```

### 1. Health check

```bash
curl -i http://localhost:8000/health -w '\n'
curl -i http://localhost:8000/health/ready -w '\n'
```

Respuesta esperada:

```json
{"status":"ok"}
```

### 2. Sin API key

```bash
curl -i http://localhost:8000/products -w '\n'
```

Respuesta esperada: `HTTP/1.1 401 Unauthorized`.

### 3. Crear producto

```bash
curl -i -X POST http://localhost:8000/products -H "$KEY" \
-H "Content-Type: application/json" \
-d '{
  "sku": "LAPTOP-001",
  "name": "Laptop Lenovo",
  "description": "Laptop para inventario de prueba",
  "category": "Tecnologia",
  "unit": "unidad"
}' -w '\n'
```

Respuesta esperada: `HTTP/1.1 201 Created`. Si se repite, `HTTP/1.1 409 Conflict` (SKU duplicado).

### 4. Listar y consultar productos

```bash
curl -i http://localhost:8000/products -H "$KEY" -w '\n'
curl -i http://localhost:8000/products/11 -H "$KEY" -w '\n'
```

Los productos `P-001` a `P-010` vienen de la semilla, así que `LAPTOP-001` es el id 11.

### 5. Actualizar producto

```bash
curl -i -X PUT http://localhost:8000/products/11 -H "$KEY" \
-H "Content-Type: application/json" \
-d '{
  "name": "Laptop Lenovo ThinkPad",
  "category": "Computadores"
}' -w '\n'
```

### 6. Registrar entrada de 10 unidades

```bash
curl -i -X POST http://localhost:8000/inventory/movements -H "$KEY" \
-H "Content-Type: application/json" \
-d '{
  "sku": "LAPTOP-001",
  "type": "RECEIPT",
  "quantity": 10,
  "reference": "ENTRADA-001"
}' -w '\n'
```

El inventario debe quedar en 10 unidades.

### 7. Consultar inventario

```bash
curl -i http://localhost:8000/inventory/LAPTOP-001 -H "$KEY" -w '\n'
```

Después del `RECEIPT` anterior debe aparecer:

```json
"quantity": 10, "available_quantity": 10, "version": 1
```

### 8. Registrar salida de 4 unidades

```bash
curl -i -X POST http://localhost:8000/inventory/movements -H "$KEY" \
-H "Content-Type: application/json" \
-d '{
  "sku": "LAPTOP-001",
  "type": "SHIPMENT",
  "quantity": 4,
  "reference": "SALIDA-001"
}' -w '\n'
```

El inventario debe pasar de 10 a 6 unidades (`version` 2).

### 9. Probar stock insuficiente

Con 6 unidades disponibles:

```bash
curl -i -X POST http://localhost:8000/inventory/movements -H "$KEY" \
-H "Content-Type: application/json" \
-d '{
  "sku": "LAPTOP-001",
  "type": "SHIPMENT",
  "quantity": 15,
  "reference": "SALIDA-INVALIDA-001"
}' -w '\n'
```

Respuesta esperada:

```text
HTTP/1.1 409 Conflict
```

```json
{"detail":"Stock insuficiente para realizar la salida"}
```

Después del error, el inventario debe continuar en 6 unidades y el movimiento rechazado no debe aparecer en el historial.

### 10. Conteo físico (`ADJUSTMENT`)

Se cuentan 5 unidades en la bodega:

```bash
curl -i -X POST http://localhost:8000/inventory/movements -H "$KEY" \
-H "Content-Type: application/json" \
-d '{
  "sku": "LAPTOP-001",
  "type": "ADJUSTMENT",
  "quantity": 5,
  "reference": "CONTEO-001"
}' -w '\n'
```

El movimiento queda con `"quantity": -1` (la diferencia) y el inventario en 5.

### 11. Consultar historial

```bash
curl -i http://localhost:8000/inventory/LAPTOP-001/movements -H "$KEY" -w '\n'
```

### 12. Borrar un producto con movimientos

```bash
curl -i -X DELETE http://localhost:8000/products/11 -H "$KEY" -w '\n'
```

Respuesta esperada: `HTTP/1.1 409 Conflict`.

## Verificar PostgreSQL

Para consultar directamente los productos almacenados:

```bash
docker compose exec db psql -U admin -d platform -c "SELECT * FROM products;"
```

Para consultar el inventario:

```bash
docker compose exec db psql -U admin -d platform -c "SELECT * FROM inventory;"
```

Para consultar los movimientos:

```bash
docker compose exec db psql -U admin -d platform -c "SELECT * FROM inventory_movements;"
```

## Detener el proyecto

```bash
docker compose down
```

Para eliminar también los volúmenes y recrear la base (esquema y semilla incluidos), **borrando los datos locales**:

```bash
make reset-db
```

## Estado del Sprint 0 (histórico)

Se verificó correctamente:

- Health check HTTP 200.
- Creación y persistencia de productos.
- CRUD de productos.
- SKU único.
- Entrada de inventario.
- Salida de inventario.
- Consulta de stock.
- Historial de movimientos.
- Validación de cantidades mayores que 0.
- Rechazo de salidas con stock insuficiente.
- Rollback sin modificar el stock ante una operación inválida.
