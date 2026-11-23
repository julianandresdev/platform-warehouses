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

## Experimento de carga con y sin caché (J-06)

100 usuarios pidiendo el mismo SKU (`GET /inventory/P-001`) durante 2 minutos, con `CACHE_ENABLED=true` y `false`. Locust, la API, PostgreSQL y Redis corren en la misma máquina (Docker Desktop), así que las cifras absolutas sirven para comparar, no como capacidad real. Se reproduce con `python3 scripts/experimento_cache.py` (ver [caching.md](../caching.md)); los CSV de Locust están en [`docs/evidencias/fase-2/`](../evidencias/fase-2/).

| Métrica | Con caché | Sin caché |
| --- | --- | --- |
| Peticiones | 213 907 | 98 566 |
| Fallos | 0 | 0 |
| RPS | 1 795,7 | 827,4 |
| P50 (ms) | 27 | 92 |
| P95 (ms) | 52 | 130 |
| P99 (ms) | 66 | 160 |
| CPU API (media %) | 104 | 111 |
| CPU PostgreSQL (media %) | 1 | 18 |
| CPU Redis (media %) | 2 | 0 |
| Transacciones en PostgreSQL (`xact_commit`) | 5 016 | 99 094 |
| Tasa de hit | 100,0 % | n/a |

Con caché el sistema sirve 2,2 veces más peticiones por segundo, el P95 baja de 130 a 52 ms y PostgreSQL recibe 20 veces menos transacciones. La CPU de la API es casi igual porque en ambos casos es el cuello de botella (un solo proceso Python al 100 %): la caché descarga a PostgreSQL, no a la API.

Una corrida de saturación (sin espera entre peticiones, 1 minuto, en [`saturacion/`](../evidencias/fase-2/saturacion/resumen.md)) da la misma tendencia: 1 271 RPS con caché contra 842 sin ella.

### Hallazgos

1. **Pool de conexiones agotado (corregido).** La primera corrida sin caché dio P95 de 30 s y 82 fallos (500): `QueuePool limit of size 5 overflow 10 reached`. FastAPI atiende los endpoints síncronos con 40 hilos y SQLAlchemy ofrecía solo 15 conexiones; los hilos esperaban una conexión y la limpieza que la libera no conseguía hilo, así que la API se atascaba hasta el timeout de 30 s. Se subió el pool a 20 + 20 (`DB_POOL_SIZE`, `DB_MAX_OVERFLOW`, más `pool_pre_ping`). Con la caché encendida el problema no aparecía porque un hit no toma conexión. Evidencia previa al ajuste: [`antes-ajuste-pool/`](../evidencias/fase-2/antes-ajuste-pool/resumen.md).
2. **Los 5 016 de "con caché" no son misses.** Con la API al 100 % de CPU, algunas llamadas a Redis superan el timeout de 0,2 s; se registran como `cache_unavailable`, responden `BYPASS` desde PostgreSQL y no cuentan en `cache_hits_total` ni `cache_misses_total`. Por eso la tasa de hit sale 100 % pero hay transacciones. En una prueba de 20 s se vieron 114 `cache_unavailable` con 34 531 hits y 29 misses. Es el fallback funcionando bajo saturación.
3. Falta la comparación con `CACHE_INVALIDATION=async` y la ventana de dato obsoleto: depende de D-04 (#18), que aún no existe.

### Las preguntas de la fase

> Nota: el enunciado de las 4 preguntas de F2 no está en el repositorio; estas son las que cubre el plan (sección F2). Hay que contrastarlas con el enunciado del profesor.

**¿Cuánto mejora la caché y por qué?** Ver la tabla: 2,2× RPS, P95 −60 %, 20× menos transacciones en PostgreSQL. Un hit se resuelve con un `GET` en Redis y no ocupa conexión de la base.

**¿Qué pasa si Redis cae?** La API responde desde PostgreSQL (`BYPASS`), registra `cache_unavailable` y las escrituras siguen dando 201. Se verificó con `docker compose stop redis`.

**¿Por qué TTL de 30 s y por qué invalidar además?** El TTL acota cuánto puede durar un dato viejo si falla el `DEL` o se da la carrera de relleno (ADR-0008); la invalidación hace que, tras un movimiento, la siguiente lectura vea el valor nuevo sin esperar al TTL.

**¿Dónde queda la ventana de dato obsoleto?** Entre una lectura que leyó antes del commit y su `SET` posterior al `DEL`: como máximo 30 s. Se documenta en el ADR-0008 y se cubre con una prueba unitaria. La comparación con la invalidación asíncrona se completará con D-04.
