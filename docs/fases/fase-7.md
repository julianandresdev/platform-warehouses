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
- E-04: Proyección CQRS desde RabbitMQ.
- E-05: Consultas globales y comparación con fanout.
- E-06: Orquestación Saga.
