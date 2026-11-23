# Caché de inventario

Cache Aside sobre Redis para `GET /inventory/{sku}`. Decisión y alternativas en [ADR-0008](adr/0008-cache-aside-con-redis.md).

## Funcionamiento

| Paso | Qué ocurre |
| --- | --- |
| Lectura, hit | Se devuelve el JSON de Redis. `X-Cache: HIT`. |
| Lectura, miss | Se lee PostgreSQL, se guarda con TTL 30 s. `X-Cache: MISS`. |
| Movimiento (RECEIPT, SHIPMENT, ADJUSTMENT) | Commit en PostgreSQL y después `DEL` de la llave. |
| Redis caído o caché apagada | Se responde desde PostgreSQL. `X-Cache: BYPASS`. |

Llave: `warehouse:{WAREHOUSE_ID}:inventory:{sku}`.

## Límites conocidos

- Una lectura que ya estaba en curso cuando se hizo el movimiento puede dejar el valor viejo en Redis hasta que expire el TTL (máximo 30 s). Ver [ADR-0008](adr/0008-cache-aside-con-redis.md). La garantía de "valor nuevo de inmediato" aplica a lecturas que empiezan después del movimiento.
- Un valor ilegible en Redis se descarta (`cache_corrupt`) y se responde desde PostgreSQL.

## Configuración

| Variable | Default | Uso |
| --- | --- | --- |
| `REDIS_URL` | vacío | URL de Redis; sin ella no hay caché. |
| `CACHE_ENABLED` | `true` | `false` apaga la caché. |
| `CACHE_TTL_SECONDS` | `30` | Vida de cada llave. |
| `REDIS_TIMEOUT_SECONDS` | `0.2` | Timeout de conexión y de operación. |

Con `docker compose`, Redis es el servicio `redis` y no tiene persistencia (es solo caché).

## Métricas

`GET /metrics` (sin API key, como `/health`) expone `cache_hits_total` y `cache_misses_total`. Los `BYPASS` no cuentan en ninguno.

## Cómo comprobarlo

```bash
docker compose up -d --build
curl -i -H "X-API-Key: dev-api-key" localhost:8000/inventory/P-001   # MISS
curl -i -H "X-API-Key: dev-api-key" localhost:8000/inventory/P-001   # HIT
docker compose stop redis
curl -i -H "X-API-Key: dev-api-key" localhost:8000/inventory/P-001   # 200, BYPASS
```

Con `CACHE_ENABLED=false docker compose up -d api` todas las lecturas salen `BYPASS` (base para el experimento de J-06).

## Experimento de carga

```bash
python3 scripts/experimento_cache.py                     # 100 usuarios, 2 min, con y sin caché
LOAD_TIME=20s python3 scripts/experimento_cache.py       # prueba rápida
LOAD_TAG=saturacion LOAD_WAIT=0 LOAD_TIME=1m python3 scripts/experimento_cache.py
```

El script recrea la API con `CACHE_ENABLED=true` y `false`, lanza Locust (`docker compose --profile load run --rm locust`) y escribe `resumen.md` y los CSV en `docs/evidencias/fase-2/`. Mide RPS, P50/P95/P99, CPU (`docker stats`), la diferencia de `pg_stat_database.xact_commit` y la tasa de hit. Resultados y lectura en [fase-2.md](fases/fase-2.md).

Escenarios del [locustfile](../tests/load/locustfile.py) (se eligen por nombre con `LOAD_SCENARIO`): `ReadSameSku` (default), `UsuarioBodega` y `ReadWriteMix`. Otras variables: `LOAD_USERS`, `LOAD_TIME`, `LOAD_SKU`, `LOAD_WAIT`.

