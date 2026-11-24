# Fase 7 — Plataforma central y CQRS

## E-03: Estructura de la plataforma central

### Componentes implementados
- Central API con FastAPI y autenticación mediante X-API-Key.
- PostgreSQL independiente con nueve tablas.
- Central Worker preparado para CQRS y Saga.
- Integración de los tres servicios mediante Docker Compose.
- Logs JSON y correlation ID.

### Endpoints implementados
- GET /health
- GET /health/ready
- POST /internal/batch-runs

### Pruebas realizadas
- Docker Compose: configuración válida.
- Central API: HTTP 200 OK.
- PostgreSQL: conexión correcta y tablas creadas.
- Autenticación: HTTP 401 sin API Key.
- Registro Batch: HTTP 201.
- Registro duplicado: HTTP 409.
- Worker: inicio, conexión y reinicio exitosos.

### Pendiente
- E-05: Consultas globales y comparación con fanout.
- E-06: Orquestación Saga.

## E-04: Proyección CQRS y endpoints globales

### Implementación
- Worker central consumidor de RabbitMQ: central.projection.
- Upsert de inventario con control de versión.
- Idempotencia mediante processed_messages.
- Heartbeats y detección stale después de 90 segundos.
- GET /global/warehouses.
- GET /global/inventory/{sku}.
- GET /global/inventory con paginación.
- Métrica projection_lag_seconds expuesta en puerto interno 9101.

### Evidencia
- Proyección de INVENTORY_UPDATED comprobada en PostgreSQL.
- Versiones antiguas descartadas.
- Mismo event_id publicado dos veces y procesado una vez.
- Heartbeat registrado correctamente.
- Endpoint por SKU: HTTP 200, cantidades consolidadas.
- SKU inexistente: HTTP 404.
- Endpoint protegido: HTTP 401 sin API Key.
- Pruebas de paginación y bodega WH-002 pendientes de verificación final.

### Preguntas del profesor
- ¿Por qué CQRS? Para separar el modelo de lectura de las escrituras.
- ¿Qué ocurre si una bodega cae? La consulta sigue respondiendo,
  pero marca como stale los datos de esa bodega.
- ¿Cómo se evitan inconsistencias? Con versiones e idempotencia.

Decisión arquitectónica: [ADR-0012](../adr/0012-proyeccion-cqrs.md).
