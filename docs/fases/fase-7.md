# Fase 7 - Plataforma central y CQRS

Lider: Esteban | Apoyo: David

Estado: En desarrollo. E-03 integrada en main.

## Que se construyo

### E-03: Estructura de la plataforma central

- Central API con FastAPI y autenticación mediante X-API-Key.
- PostgreSQL independiente con nueve tablas.
- Central Worker preparado para CQRS y Saga.
- Integración de los tres servicios mediante Docker Compose.
- Logs JSON y correlation ID.

### Endpoints implementados

- GET /health
- GET /health/ready
- POST /internal/batch-runs

## Cierre de la fase

Pendiente de integrar y validar las actividades restantes.

## Decisiones

| Decision | Elegido | Por que |
| --- | --- | --- |
| API central | FastAPI | Mantener la tecnología del proyecto |
| Base de datos | PostgreSQL independiente | Separar la central de las bodegas |
| Procesamiento asíncrono | Central Worker | Preparar CQRS y Saga |

## Pruebas realizadas

### E-03

- Docker Compose: configuración válida.
- Central API: HTTP 200 OK.
- PostgreSQL: conexión correcta y tablas creadas.
- Autenticación: HTTP 401 sin API Key.
- Registro Batch: HTTP 201.
- Registro duplicado: HTTP 409.
- Worker: inicio, conexión y reinicio exitosos.

## Resultados y evidencias

Las pruebas funcionales de E-03 fueron exitosas.

## Preguntas del profesor

## Pendientes

- E-04: Integración de la proyección CQRS.
- E-05: Integración de consultas globales y fanout.
- E-06: Integración del orquestador Saga.
