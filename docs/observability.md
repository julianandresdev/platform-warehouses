# Observabilidad

Tres piezas: logs estructurados con correlation ID, métricas en Prometheus y dashboards en Grafana (S-07, [ADR-0016](adr/0016-prometheus-y-grafana.md)).

## Logs estructurados

Todos los servicios escriben una línea JSON por evento con `timestamp`, `service`, `warehouse_id`, `level`, `event` y `correlation_id`. Las APIs registran cada request con `method`, `path`, `status` y `duration_ms`.

## Correlation ID

El middleware de las APIs lee `X-Correlation-ID` o genera uno, lo guarda para todo el request y lo copia en los eventos que se publican. Así una transferencia se sigue de punta a punta por un solo valor:

```bash
docker compose -p warehouses-demo -f infrastructure/compose/compose.distributed.yml \
  -f infrastructure/compose/compose.central.yml logs --no-color | grep COR-DEMO-1 | cut -d'|' -f2- | jq -c '{service, event, status}'
```

Los objetos que escriben el batch y los reportes llevan el mismo valor como metadato `correlation-id` en el bucket. Los IDs no se usan como etiqueta de métrica.

## Métricas

| Origen | Métricas | Puerto |
| --- | --- | --- |
| API de bodega (`/metrics`) | `http_requests_total`, `http_request_duration_seconds`, `cache_hits_total`, `cache_misses_total` | 8000 |
| API central (`/metrics`) | `http_requests_total`, `http_request_duration_seconds` | 8000 |
| Worker central | `projection_lag_seconds{warehouse_id}` | 9101 |
| RabbitMQ (plugin) | mensajes listos y sin confirmar por cola, consumidores, publicados, confirmados, conexiones | 15692 |
| `redis_exporter` (uno por bodega) | memoria, clientes, comandos, aciertos y fallos del keyspace | 9121 |
| `postgres_exporter` (WH-002 y central) | `warehouse_outbox_*`, `central_outbox_*`, `central_transfers_total{status}` | 9187 |

La etiqueta `route` de `http_requests_total` es la plantilla de la ruta (`/inventory/{sku}`); las rutas que no existen quedan juntas como `unmatched`.

Los workers de bodega no exponen `/metrics` propio; se observan por las colas de RabbitMQ y por el outbox pendiente.

## Prometheus

[`infrastructure/observability/prometheus.yml`](../infrastructure/observability/prometheus.yml), con scrape cada 5 s. Las réplicas de WH-002 se descubren por DNS (`dns_sd_configs`), así que `--scale wh002_api=3` no requiere cambiar nada.

```bash
docker compose -p warehouses-demo \
  -f infrastructure/compose/compose.distributed.yml \
  -f infrastructure/compose/compose.central.yml \
  -f infrastructure/compose/compose.obs.yml --profile obs up -d --build
```

Prometheus queda en <http://localhost:9090> (Status → Targets).

## Grafana

<http://localhost:3000> (`admin` / `admin`, solo local). El datasource y los dashboards se aprovisionan desde [`infrastructure/observability/grafana/`](../infrastructure/observability/grafana/), carpeta «Warehouse Cloud Platform»:

| Dashboard | Qué muestra |
| --- | --- |
| APIs (`wp-apis`) | requests por segundo, latencia p95, errores 5xx, rutas más usadas, aciertos y fallos de la caché, instancias arriba |
| Redis (`wp-redis`) | memoria, clientes, comandos por segundo, keyspace hits/misses, claves |
| RabbitMQ (`wp-rabbitmq`) | mensajes listos y sin confirmar por cola, publicados/confirmados, consumidores, colas sin consumidor |
| Workers (`wp-workers`) | outbox pendiente y su antigüedad (WH-002 y central), retraso de la proyección, colas de comandos y reportes |
| Saga (`wp-saga`) | transferencias por estado, en curso, completadas/canceladas/fallidas, `POST /transfers` y latencia de la central |

## Alertas

No hay reglas de alerta: el alcance de S-07 son las métricas y los dashboards.

## Evidencia (S-07)

Entorno: `compose.distributed.yml` + `compose.central.yml` + `compose.obs.yml`, 26 de noviembre de 2026, con tráfico de `curl` (lecturas en las tres bodegas y transferencias `WH-001 → WH-002/WH-003`).

- **Targets:** los 13 quedan `up` (central-api, central-worker, 2 postgres, prometheus, rabbitmq, rabbitmq-queues, 3 redis y las 3 APIs de bodega).
- **Consultas de los dashboards:** de las 38 expresiones de los 5 dashboards, 37 devuelven datos; la que queda vacía es «Errores 5xx por segundo», porque no hubo errores 5xx.
- **Dashboard de la Saga con datos en vivo:** durante el tráfico mostró 9 transferencias `COMPLETED` y 2 en `DESTINATION_PENDING`, `POST /transfers` a 0,24 req/s y latencia p95 de la central entre 10 y 39 ms; el outbox central en 0 pendientes.
- **Dashboard de APIs:** requests por segundo y latencia p95 de las cuatro APIs (`wh001-api` 4,9 ms; `central-api` 21 ms).
- **Prueba de carga con los dashboards en vivo:** Locust (`UsuarioBodega`, 100 usuarios, 75 s) contra WH-001: 57.065 requests, 0 fallos, 769 req/s, p95 100 ms. Mientras corría, el dashboard de APIs mostró `wh001-api` a 646 req/s con p95 de 75 ms (máximo 88 ms), y las otras APIs sin cambio. Captura: [`s07-grafana-apis-bajo-carga.jpg`](evidencias/fase-11/s07-grafana-apis-bajo-carga.jpg).
