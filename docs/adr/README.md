# Architecture Decision Records (ADR)

Los ADR registran el contexto, las alternativas,
las decisiones arquitectonicas y sus consecuencias.

Utilizar la [plantilla](0000-plantilla.md) para
documentar nuevas decisiones.

## Indice de decisiones

| ADR | Tema | Responsable previsto | Estado |
| --- | --- | --- | --- |
| [0001](0001-fastapi-como-framework.md) | FastAPI y SQLAlchemy | Julian | Disponible |
| [0002](0002-una-imagen-por-dominio.md) | Una imagen por dominio | Julian | Disponible |
| [0003](0003-schema-sql-como-fuente-de-verdad.md) | Schema SQL y migraciones | Julian | Disponible |
| [0004](0004-control-de-concurrencia-en-movimientos.md) | Control de concurrencia | Julian | Disponible |
| [0005](0005-topologia-rabbitmq.md) | Topologia RabbitMQ | David | Disponible |
| [0006](0006-patron-outbox.md) | Transactional Outbox | David | Disponible |
| [0007](0007-una-base-por-bodega.md) | Una base por bodega | Santiago | Borrador pendiente de revisión |
| [0008](0008-cache-aside-con-redis.md) | Cache Aside con Redis | Julian | Disponible |
| [0009](0009-nginx-y-health-checks-pasivos.md) | Nginx y health checks pasivos | Santiago | Borrador pendiente de revisión |
| [0010](0010-autenticacion-api-key.md) | API Key | Esteban | Pendiente de revision |
| [0011](0011-minio-local-y-s3-en-aws.md) | MinIO y S3 | Santiago | Borrador pendiente de revisión |
| [0012](0012-proyeccion-cqrs.md) | CQRS y Heartbeat | Esteban | Recuperado de E-04/E-06 |
| [0013](0013-saga-orquestada.md) | Saga orquestada | Esteban | Recuperado de E-06 |
| [0014](0014-batch-csv-s3.md) | Batch y S3 | Julian / Santiago | Propuesta pendiente |
| 0015 | Reintentos, DLQ e idempotencia | David | Pendiente |
| 0016 | Prometheus y Grafana | Santiago | Pendiente |
| [0017](0017-lambda-validacion-eventos.md) | Lambda fuera de la VPC | Santiago | Propuesta pendiente |
| 0018 | Despliegue AWS Learner Lab | Santiago | Pendiente |
| 0019 | MQTT, QoS e IoT | David | Pendiente |

## Decisiones adicionales

- [Idempotencia de comandos Saga en bodega](0020-idempotencia-comandos-bodega.md):
  documento de Julian correspondiente a J-07.

## Inconsistencias pendientes

- El ADR-0014 de Batch no confirma el cumplimiento
  del contrato original de lectura mediante APIs.
- Los ADR-0014 de Batch y 0017 de Lambda contienen
  propuestas pendientes de aprobacion.

## Consolidacion

Los documentos recuperados conservan su contenido original.
Se debe verificar su version definitiva despues del merge
de las ramas correspondientes.

La existencia de un ADR no implica que la funcionalidad
este integrada, probada o aprobada.

La consolidacion definitiva requiere resolver las
inconsistencias y completar los ADR pendientes.
