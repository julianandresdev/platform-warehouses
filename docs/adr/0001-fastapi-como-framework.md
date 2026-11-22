# ADR-0001: FastAPI como framework de la API de bodega

- Estado: aceptado
- Fecha: 2026-11-22
- Autor: Julian

## Contexto

Cada bodega expone una API REST (productos, inventario, movimientos) que más adelante también debe emitir eventos, servir de blanco de pruebas de carga y correr varias veces desde la misma imagen. El equipo trabaja en Python y necesita validación de entradas, documentación de la API y buen rendimiento con pocos recursos.

## Alternativas

| Alternativa | A favor | En contra |
| --- | --- | --- |
| **FastAPI** | Validación con Pydantic, OpenAPI y `/docs` automáticos, inyección de dependencias (la usamos para la API key y la sesión de base), soporte `async` para las fases con RabbitMQ | Es más joven que Flask y Django |
| Flask | Muy simple, el equipo lo conoce | Validación y documentación se agregan con extensiones; sin tipado de las respuestas |
| Django REST Framework | ORM, admin y autenticación incluidos | Pesado para un servicio pequeño; el ORM es distinto del que usan los demás servicios |

## Decisión

FastAPI con SQLAlchemy y PostgreSQL (`psycopg2`). Una sola imagen de `warehouse-api` configurada por variables de entorno (`WAREHOUSE_ID`, `DATABASE_URL`, `API_KEY`).

## Consecuencias

- Los esquemas Pydantic validan el cuerpo de cada petición (`quantity` > 0 en entradas y salidas) y responden 422 sin llegar a la base.
- La documentación interactiva queda gratis en `/docs`.
- Las rutas que mutan o leen datos cuelgan de un router con la dependencia `X-API-Key`; `/health` y `/health/ready` quedan fuera.
- Los endpoints actuales son síncronos; pasar a `async` se evalúa cuando el trabajo con RabbitMQ lo pida.
