# ADR-0008: Cache Aside con Redis e invalidación síncrona (primera versión)

- Estado: aceptado (se ampliará con la invalidación asíncrona de la Fase 6)
- Fecha: 2026-11-22
- Autor: Julian

## Contexto

Las lecturas de inventario (`GET /inventory/{sku}`) son mucho más frecuentes que las escrituras. Hace falta acelerarlas sin que Redis se vuelva fuente de verdad ni punto de falla: si Redis cae, la API debe seguir funcionando.

## Alternativas

| Alternativa | A favor | En contra |
| --- | --- | --- |
| **Cache Aside** (la API lee Redis, y ante un miss lee PostgreSQL y guarda) | Simple; Redis es opcional; el dato siempre se puede reconstruir | Hay una ventana donde el dato puede estar viejo |
| Write-through (escribir en Redis y en PostgreSQL) | Caché siempre tibia | La escritura depende de Redis; dos escrituras que pueden divergir |
| Solo TTL, sin invalidar | Nada que mantener | Lecturas viejas hasta 30 s tras cada movimiento |
| Invalidar **antes** del commit | Parece más seguro | Una lectura concurrente vuelve a cachear el valor viejo y queda hasta el TTL |

## Decisión

- Llave `warehouse:{WAREHOUSE_ID}:inventory:{sku}`, valor JSON de la respuesta, TTL 30 s. No se cachean los 404.
- Lectura: hit → se devuelve; miss → PostgreSQL y `SET ... EX 30`.
- **Invalidación síncrona (`DEL`) después del commit** del movimiento. Si se borrara antes, una lectura que llegue entre el `DEL` y el commit leería el valor viejo de PostgreSQL y lo volvería a guardar, y la caché quedaría vieja hasta que expire. Después del commit, cualquier lectura posterior ya ve el valor nuevo.
- **Fallback**: cualquier `RedisError` se registra (`cache_unavailable`) y la lectura sale de PostgreSQL con `X-Cache: BYPASS`. La escritura nunca falla por Redis: el commit ya ocurrió y, si el `DEL` falla, el TTL acota el dato viejo a 30 s.
- Timeouts de 0,2 s (`socket_timeout` y `socket_connect_timeout`) con pool de conexiones, para que una caída no cuelgue la API.
- `CACHE_ENABLED=false` apaga la caché (`X-Cache: BYPASS`); sirve para el experimento ON/OFF de J-06.
- Métricas `cache_hits_total` y `cache_misses_total` en `/metrics`.

## Consecuencias

- Queda una ventana mínima (milisegundos) entre el commit y el `DEL` en la que una lectura puede ver el dato anterior; es inherente a Cache Aside y aceptable aquí.
- Si Redis está caído al hacer el `DEL`, el dato viejo puede durar hasta 30 s.
- Con varias réplicas de la API de la misma bodega la invalidación sigue funcionando porque todas comparten el Redis de esa bodega.
- La invalidación asíncrona por eventos (F6) deberá mantener las mismas garantías o documentar la diferencia.
