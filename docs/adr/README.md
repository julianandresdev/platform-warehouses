# Architecture Decision Records (ADR)

Los ADR registran las decisiones arquitectónicas del
proyecto Warehouse Cloud Platform.

Cada documento debe explicar el contexto, las alternativas
consideradas, la decision y sus consecuencias.

## Plantilla

Utilizar la [plantilla de ADR](0000-plantilla.md).

Formato de nombre: NNNN-titulo-corto.md.

## Índice de decisiones arquitectónicas

Las fechas corresponden al cronograma original.
El estado indica la disponibilidad del documento en esta rama.

| ADR | Tema | Autor | Fecha prevista | Estado |
| --- | --- | --- | --- | --- |
| [0001](0001-fastapi-como-framework.md) | FastAPI + SQLAlchemy | Julian | 13 nov | Existente |
| [0002](0002-una-imagen-por-dominio.md) | Una imagen por dominio con varios comandos | Julian | 13 nov | Existente |
| [0003](0003-schema-sql-como-fuente-de-verdad.md) | schema.sql y migraciones en vez de create_all | Julian | 14 nov | Existente |
| [0004](0004-control-de-concurrencia-en-movimientos.md) | Control de concurrencia en movimientos de inventario | Julian | 14 nov | Existente |
| [0005](0005-topologia-rabbitmq.md) | Topología de RabbitMQ | David | 15 nov | Existente |
| [0006](0006-patron-outbox.md) | Patrón Outbox | David | 16 nov | Existente |
| 0007 | Una base por bodega | Santiago | 17 nov | Pendiente |
| [0008](0008-cache-aside-con-redis.md) | Cache Aside, TTL e invalidación síncrona contra asíncrona | Julian | 17 nov | Existente |
| 0009 | Nginx como balanceador y health checks pasivos | Santiago | 18 nov | Pendiente |
| 0010 | API Key; usuarios y operadores fuera de alcance | Esteban | 18 nov | Pendiente |
| 0011 | MinIO en local, S3 en AWS | Santiago | 19 nov | Pendiente |
| [0012](0012-proyeccion-cqrs.md) | Read Model, CQRS y heartbeat | Esteban | 20 nov | Existente |
| 0013 | Saga orquestada contra coreografía | Esteban | 21 nov | Pendiente de integración |
| 0014 | El Batch lee las bodegas por API | Julian | 21 nov | Pendiente |
| 0015 | Reintentos, DLQ y clasificación de errores | David | 21 nov | Pendiente |
| 0016 | Prometheus + Grafana | Santiago | 22 nov | Pendiente |
| 0017 | Lambda fuera de la VPC | Santiago | 23 nov | Pendiente |
| 0018 | Despliegue en AWS Learner Lab | Santiago | 24 nov | Pendiente |
| 0019 | MQTT, QoS y deduplicación IoT | David | 24 nov | Pendiente |
| [0020](0020-idempotencia-comandos-bodega.md) | Idempotencia de comandos Saga en la bodega | Julian | Fuera del cronograma original | Existente |

## Observaciones

- Los ADR pendientes deben ser escritos por sus responsables.
- Los ADR desarrollados en otras ramas se enlazarán
  cuando sean integrados.
- No se deben eliminar decisiones anteriores sin
  documentar su reemplazo.
- El índice se consolidará definitivamente durante E-08.
