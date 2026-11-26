# Atasco de la API de bodega bajo sobrecarga (J-06, visto en J-09)

Entorno: Docker Compose local, WH-002 con 3 réplicas detrás de nginx, Locust `UsuarioBodega`, 26 de noviembre de 2026. Una corrida por configuración (sin repeticiones salvo donde se indica).

## El síntoma

En la evidencia de J-09, tras una carga de 500 usuarios o más, las réplicas de WH-002 quedaban con sus conexiones `idle in transaction`, `/health` dejaba de responder y no se recuperaban solas aunque terminara la carga.

## Qué se probó

Dos preguntas distintas: (A) ¿por qué falla WH-002 con 500 usuarios? y (B) ¿por qué una réplica no se recupera tras una sobrecarga?

### A. 500 usuarios, 90 s

| Configuración | Requests | Fallos | Comentario |
| --- | ---: | ---: | --- |
| `main`, nginx tal cual (`max_fails=1`) — corrida de J-09 | 131.727 | 106.225 (81 %) | |
| `main`, nginx con `max_fails=0` (no saca réplicas del pool) | 167.190 | **0** | 2158 req/s, P95 420 ms |
| Arreglo de la API, nginx tal cual | 234.147 | 52.750 (23 %) | |
| Arreglo de la API, nginx sin `http_503` en `proxy_next_upstream` | 147.208 | 102.708 (70 %) | peor: no ayuda |
| Arreglo de la API, nginx con `max_fails=0` | 99.594 | 61 (0,06 %) | 1131 req/s, P95 230 ms |

Con 500 usuarios, **lo que tumba a WH-002 no es la API sino la detección pasiva de nginx**: con `max_fails=1 fail_timeout=10s`, un solo timeout saca una réplica del pool durante 10 s y, al caer las tres, todo da 502 (`no live upstreams`). Sin ese marcado la API aguanta los 500 usuarios, incluso sin ningún arreglo. Esto corrige lo que decía la primera versión del análisis de J-09, que atribuía el colapso de 500 usuarios al atasco de la API.

### B. 5000 usuarios, 90 s, y recuperación a los 60 s

Después de la carga se mira `pg_stat_activity` de WH-002 y `/health` de cada réplica; luego una carga de prueba de 100 usuarios durante 20 s.

| Configuración | Conexiones `idle in transaction` a los 60 s | Réplicas sin responder `/health` | Prueba de 100 usuarios |
| --- | ---: | --- | --- |
| `main` (sin cambios) | 40 | 1 de 3 | 27 fallos de 18.349 |
| `get_db` async + `DB_POOL_TIMEOUT=5` + 503 por pool agotado | 40 | 1 de 3 | 43 fallos de 17.929 |
| lo anterior + `uvicorn --limit-concurrency 200` (**este PR**), corrida 1 | **0** | **ninguna** | 30 fallos de 18.610 |
| lo anterior, corrida 2 | **0** | **ninguna** | 34 fallos de 18.567 |

En la corrida de J-09 con `main` las tres réplicas quedaron atascadas (120 conexiones). En las de esta tabla fue una; la diferencia no se investigó.

## Qué causa el atasco

No es solo la limpieza de la sesión. El registro de la réplica atascada muestra requests que terminan con **503 tras 185 s** (`duration_ms: 184859`): bajo sobrecarga, los requests se acumulan en la cola del pool de 40 hilos y la réplica tarda minutos en drenarla; mientras tanto sus 40 conexiones siguen tomadas y `/health`, que también usa un hilo, no responde. Limitar la concurrencia en uvicorn hace que lo que no cabe se rechace al instante con 503 en lugar de encolarse.

## Qué cambia este PR

- `get_db` pasa a `async`: la limpieza de la sesión corre en el bucle de eventos y no necesita un hilo libre (la causa que describía J-06).
- `DB_POOL_TIMEOUT` (5 s por defecto en lugar de 30) y un manejador que responde **503 con `Retry-After`** cuando el pool se agota, en lugar de 500.
- `uvicorn --limit-concurrency` con `UVICORN_LIMIT_CONCURRENCY=200` por defecto.

La tabla B muestra que el último cambio es el que logra la recuperación; los dos primeros solos no bastaron en la prueba. Se conservan porque quitan la limpieza que dependía de un hilo y acotan la espera por una conexión, pero no se probó cada uno por separado contra el límite de concurrencia.

## Lo que no se arregla aquí

- **nginx `max_fails=1`** (S-04, ADR-0009): sigue convirtiendo cualquier timeout en una caída total del pool. `max_fails=0` desactivaría el failover pasivo que pide el criterio de S-04, así que no se cambió; hace falta decidir otro valor (p. ej. más fallos tolerados, o `fail_timeout` más corto) y medirlo.
- **El `200` de concurrencia** es un valor razonable (≈ 5 veces los 40 hilos) pero no está afinado.
- Las réplicas siguen devolviendo 503 a la mayoría de los requests durante una sobrecarga de 5000 usuarios; lo que cambia es que se recuperan en cuanto cesa.
