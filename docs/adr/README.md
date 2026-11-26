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
| [0011](0011-minio-local-y-s3-en-aws.md) | MinIO y S3 | Santiago | Disponible (S-05, PR #62) |
| [0012](0012-proyeccion-cqrs.md) | CQRS y Heartbeat | Esteban | Recuperado de E-04/E-06 |
| [0013](0013-saga-orquestada.md) | Saga orquestada | Esteban | Recuperado de E-06 |
| [0014](0014-batch-lee-bodegas-por-api.md) | El batch lee las bodegas por API | Julian | Disponible (J-08, PR #63) |
| [0015](0015-reintentos-dlq-idempotencia.md) | Reintentos, DLQ e idempotencia | David | Implementado en D-05; validación local |
| [0016](0016-prometheus-y-grafana.md) | Prometheus y Grafana | Santiago | Disponible (S-07) |
| [0017](0017-lambda-fuera-de-la-vpc.md) | Lambda fuera de la VPC | Santiago | Disponible (S-08, PR #65) |
| [0018](0018-despliegue-aws-learner-lab.md) | Despliegue AWS Learner Lab | Santiago | Disponible (S-09) |
| [0019](0019-mqtt-qos-y-deduplicacion.md) | MQTT, QoS e IoT | David | Borrador pendiente de revisión |
