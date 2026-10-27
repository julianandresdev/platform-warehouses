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

Se implementó el manejo de inventario para una bodega.

Endpoints:

- `GET /inventory/{product_id}`
- `POST /inventory/movements`
- `GET /inventory/{product_id}/movements`

Los movimientos permitidos son:

- `RECEIPT`: entrada de unidades al inventario.
- `SHIPMENT`: salida de unidades del inventario.

La cantidad de un movimiento debe ser mayor que 0.

### Control de stock

Los movimientos de inventario se procesan mediante una transacción.

Para una salida `SHIPMENT`:

1. Se consulta y bloquea el registro del inventario.
2. Se verifica que exista stock suficiente.
3. Se descuenta la cantidad.
4. Se registra el movimiento.
5. Se confirma la transacción.

Si no existe stock suficiente, la API responde HTTP 400 y la operación se revierte, evitando que el inventario quede con cantidades negativas.

## Estructura principal

```text
platform-warehouses/
├── docker-compose.yaml
├── .env.example
└── src/
    ├── Dockerfile
    ├── app.py
    ├── database.py
    ├── models.py
    ├── schemas.py
    ├── services.py
    └── requirements.txt
```

### Archivos principales

`app.py`

Contiene la aplicación FastAPI y los endpoints HTTP.

`database.py`

Configura SQLAlchemy, la conexión con PostgreSQL, las sesiones y la creación inicial de las tablas.

`models.py`

Contiene los modelos SQLAlchemy:

- Product
- Inventory
- InventoryMovement

`schemas.py`

Contiene los modelos Pydantic utilizados para validar las solicitudes y respuestas de la API.

`services.py`

Contiene la lógica de negocio, incluyendo:

- CRUD de productos.
- Consulta de inventario.
- Historial de movimientos.
- Procesamiento transaccional de entradas y salidas.
- Validación de stock.

## Ejecución

Desde la raíz del proyecto ejecutar:

```bash
docker compose up --build
```

Docker Compose inicia:

- PostgreSQL en el puerto 5432.
- FastAPI en el puerto 5000.

El servicio de la API espera a que PostgreSQL esté saludable antes de iniciar.

La API queda disponible en:

```text
http://localhost:5000
```

La documentación interactiva de FastAPI está disponible en:

```text
http://localhost:5000/docs
```

## Pruebas

### 1. Health check

```bash
curl -i http://localhost:5000/health -w '\n'
```

Respuesta esperada:

```json
{"status":"ok"}
```

### 2. Crear producto

```bash
curl -i -X POST http://localhost:5000/products \
-H "Content-Type: application/json" \
-d '{
  "sku": "LAPTOP-001",
  "name": "Laptop Lenovo",
  "description": "Laptop para inventario de prueba",
  "category": "Tecnologia",
  "unit": "unidad"
}' -w '\n'
```

Respuesta esperada:

```text
HTTP/1.1 201 Created
```

### 3. Listar productos

```bash
curl -i http://localhost:5000/products -w '\n'
```

### 4. Consultar producto

```bash
curl -i http://localhost:5000/products/1 -w '\n'
```

### 5. Actualizar producto

```bash
curl -i -X PUT http://localhost:5000/products/1 \
-H "Content-Type: application/json" \
-d '{
  "name": "Laptop Lenovo ThinkPad",
  "category": "Computadores"
}' -w '\n'
```

### 6. Registrar entrada de 10 unidades

```bash
curl -i -X POST http://localhost:5000/inventory/movements \
-H "Content-Type: application/json" \
-d '{
  "product_id": 1,
  "warehouse_id": 1,
  "type": "RECEIPT",
  "quantity": 10,
  "reference": "ENTRADA-001"
}' -w '\n'
```

El inventario debe quedar en 10 unidades.

### 7. Consultar inventario

```bash
curl -i http://localhost:5000/inventory/1 -w '\n'
```

Después del `RECEIPT` anterior debe aparecer:

```json
"quantity": 10
```

### 8. Registrar salida de 4 unidades

```bash
curl -i -X POST http://localhost:5000/inventory/movements \
-H "Content-Type: application/json" \
-d '{
  "product_id": 1,
  "warehouse_id": 1,
  "type": "SHIPMENT",
  "quantity": 4,
  "reference": "SALIDA-001"
}' -w '\n'
```

El inventario debe pasar de 10 a 6 unidades.

### 9. Probar stock insuficiente

Con 6 unidades disponibles:

```bash
curl -i -X POST http://localhost:5000/inventory/movements \
-H "Content-Type: application/json" \
-d '{
  "product_id": 1,
  "warehouse_id": 1,
  "type": "SHIPMENT",
  "quantity": 15,
  "reference": "SALIDA-INVALIDA-001"
}' -w '\n'
```

Respuesta esperada:

```text
HTTP/1.1 400 Bad Request
```

```json
{"detail":"Stock insuficiente para realizar la salida"}
```

Después del error, el inventario debe continuar en 6 unidades.

### 10. Consultar historial

```bash
curl -i http://localhost:5000/inventory/1/movements -w '\n'
```

El movimiento rechazado por stock insuficiente no debe aparecer en el historial.

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

Para eliminar también los volúmenes y reiniciar completamente la base de datos:

```bash
docker compose down -v
```

## Estado del Sprint 0

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
