# ADR-0016 — Prometheus y Grafana para observabilidad

## Estado

Aceptado. Implementado en S-07 (issue #28). Responsable asignado: Santiago.

## Contexto

Los logs enlazan una operación concreta mediante su identificador de correlación y los resúmenes de Locust describen el resultado desde el cliente. Para saber dónde se satura el sistema durante una prueba de carga hacen falta series temporales por componente: APIs, Redis, RabbitMQ, workers y Saga.

## Alternativas

| Alternativa | A favor | En contra |
| --- | --- | --- |
| **Prometheus + Grafana en Compose (profile `obs`)** | Estándar, se levanta con un comando, dashboards como JSON en el repo, sin cuenta ni costo | Dos contenedores más y almacenamiento local (retención de 2 días) |
| CloudWatch | Ya existe en AWS | No sirve en local; las pruebas de carga corren en Compose |
| Solo logs y los CSV de Locust | Sin infraestructura nueva | No muestran colas, memoria ni retraso de la proyección durante la corrida |

## Decisión

- Profile `obs` en [`compose.obs.yml`](../../infrastructure/compose/compose.obs.yml), que se suma a los otros dos Compose. No arranca con `docker compose up`.
- Prometheus ([`prometheus.yml`](../../infrastructure/observability/prometheus.yml)) recoge: `/metrics` de las APIs de bodega y de la central, el worker central (`projection_lag_seconds`, puerto 9101), el plugin Prometheus de RabbitMQ (15692, agregado y por cola), un `redis_exporter` por bodega y un `postgres_exporter` para WH-002 y para la central. Las réplicas de WH-002 se descubren por el DNS de Docker.
- Las APIs registran `http_requests_total` y `http_request_duration_seconds` con la etiqueta `route` (la plantilla de la ruta, no la URL) desde `common/metrics.py`.
- Las consultas propias de `postgres_exporter` publican el outbox pendiente (WH-002 y central) y las transferencias por estado de la Saga.
- Grafana se aprovisiona con el datasource y cinco dashboards JSON del repo: APIs, Redis, RabbitMQ, Workers y Saga.
- Se conserva el correlation ID solo en los logs: las etiquetas de las métricas se mantienen acotadas.

## Consecuencias

- Los workers de bodega (outbox, comandos, caché, reportes) no exponen `/metrics` propio. Se observan por sus efectos: colas de RabbitMQ, outbox pendiente y su antigüedad. Solo el worker central expone métricas directas.
- El outbox pendiente solo se mide para WH-002 y la central, como pide el issue. WH-001 y WH-003 no tienen exporter de PostgreSQL.
- `GET /metrics` no pide `X-API-Key` (ya era así en las bodegas). Está pensado para la red interna del Compose; los puertos 9090 y 3000 se publican solo en `127.0.0.1`.
- Grafana usa `admin/admin` por defecto, solo para local (`GRAFANA_USER` y `GRAFANA_PASSWORD` lo cambian).
- Las imágenes llevan versión fija: `prom/prometheus:v2.55.1`, `grafana/grafana:11.3.0`, `oliver006/redis_exporter:v1.66.0` y `prometheuscommunity/postgres-exporter:v0.15.0`.

## Validación

Ver [observability.md](../observability.md): los 13 targets quedan `up`, las consultas de los 5 dashboards devuelven datos con tráfico real y se comprobó el dashboard de la Saga con transferencias en curso. La prueba de carga con los dashboards en vivo la hace J-09.
