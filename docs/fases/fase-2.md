# Fase 2 — Redis con Cache Aside

## Qué se hizo (J-05)

- Servicio `redis` (`redis:7-alpine`, sin persistencia) en `docker-compose.yaml`; `REDIS_URL` y `CACHE_ENABLED` en la API. El compose distribuido ya trae un Redis por bodega.
- `services/warehouse-api/cache.py`: cliente con pool y timeouts de 0,2 s, lectura/escritura/invalidación que nunca lanzan.
- `GET /inventory/{sku}`: hit → Redis; miss → PostgreSQL + `SET EX 30`; header `X-Cache: HIT|MISS|BYPASS`.
- Invalidación (`DEL`) después del commit en `process_inventory_movement`.
- `/metrics` con `cache_hits_total` y `cache_misses_total`.
- Documentación: [ADR-0008](../adr/0008-cache-aside-con-redis.md) y [caching.md](../caching.md).

## Evidencia

```text
GET /inventory/P-001  -> 200 X-Cache: MISS
GET /inventory/P-001  -> 200 X-Cache: HIT
POST SHIPMENT 1       -> 201
GET /inventory/P-001  -> 200 X-Cache: MISS, quantity 99 (valor nuevo de inmediato)
docker compose stop redis
GET /inventory/P-001  -> 200 X-Cache: BYPASS (74 ms)
POST RECEIPT 1        -> 201 (la escritura no depende de Redis)
```

Log con Redis caído: `{"level": "WARNING", "event": "cache_unavailable", "operation": "get", "sku": "P-001", ...}`.

Pruebas: `pytest tests/unit` (caché con fakeredis, Redis caído, TTL) y `pytest tests/integration` contra la API levantada.

## Preguntas del profesor

### ¿Por qué invalidar después del commit y no antes?

Si se borra la llave antes del commit, una lectura que llegue en ese instante lee de PostgreSQL el valor viejo (el commit aún no ocurrió) y lo guarda otra vez: la caché queda vieja hasta que expire el TTL. Borrando después del commit, toda lectura posterior ya encuentra el valor nuevo. Detalle en el ADR-0008.

### ¿Qué pasa si Redis cae?

La API sigue respondiendo desde PostgreSQL (`X-Cache: BYPASS`), registra `cache_unavailable` y las escrituras no se ven afectadas. Los timeouts de 0,2 s evitan que la caída cuelgue las peticiones.
