# Evidencia de F11 — escenarios de carga (J-09)

Entorno: Docker Compose local (10 CPU y 7,7 GiB para Docker), 26 de noviembre de 2026, con `compose.distributed.yml` + `compose.central.yml` + `compose.obs.yml` + `compose.load.yml`. Locust 2.32.5 en contenedores, headless, 90 s por corrida. Cada corrida deja su CSV (`*_stats.csv`, `*_stats_history.csv`, `*_failures.csv`), `docker-stats.txt` (a mitad de la corrida) y capturas de los cinco dashboards de Grafana. Tabla completa: [resumen.md](resumen.md).

Se reproducen con [`scripts/fase-11/correr.sh <escenario>`](../../../scripts/fase-11/correr.sh) y se resumen con `scripts/fase-11/resumen.py`.

## Resultados

| Escenario | Corrida | Usuarios | Req/s | Fallos | P50 | P95 | P99 |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Redis OFF | WH-001, `ReadSameSku`, sin espera | 100 | 468,9 | 0 | 150 ms | 550 ms | 1200 ms |
| Redis ON | WH-001, `ReadSameSku`, sin espera | 100 | 785,7 | 0 | 110 ms | 240 ms | 370 ms |
| 1 instancia | WH-002 por nginx, `UsuarioBodega` | 200 | 963,0 | 0 | 81 ms | 240 ms | 510 ms |
| 3 instancias | WH-002 por nginx, `UsuarioBodega` | 200 | 995,1 | 0 | 59 ms | 320 ms | 610 ms |
| Multibodega WH-001 | `UsuarioBodega` | 50 | 389,9 | 0 | 12 ms | 100 ms | 270 ms |
| Multibodega WH-002 (3 instancias) | `UsuarioBodega` | 800 | 1397,5 | 110.838 de 126.091 | 83 ms | 800 ms | 15.000 ms |
| Multibodega WH-003 | `UsuarioBodega` | 20 | 180,6 | 0 | 4 ms | 30 ms | 120 ms |
| Rampa 100 | WH-002, 3 instancias | 100 | 880,3 | 0 | 3 ms | 46 ms | 200 ms |
| Rampa 500 | WH-002, 3 instancias | 500 | 1462,9 | 106.225 de 131.727 | 14 ms | 390 ms | 15.000 ms |
| Rampa 1000 | WH-002, 3 instancias | 1000 | 3855,5 | 334.514 de 347.345 | 4 ms | 58 ms | 630 ms |
| Rampa 5000 | WH-002, 3 instancias | 5000 | 4919,1 | 429.315 de 432.810 | 450 ms | 1300 ms | 15.000 ms |

En las corridas con fallos, los «Req/s» incluyen los 502 que nginx devuelve de inmediato: no son capacidad útil.

## Lo que se observó

1. **Redis.** Con la caché activada WH-001 pasó de 468,9 a 785,7 req/s (+68 %) y el P95 bajó de 550 a 240 ms. Los resultados históricos de F2 (827,4 → 1795,7 req/s) se hicieron con otra configuración y no son comparables punto a punto.
2. **1 contra 3 instancias de WH-002.** Con 200 usuarios no hubo diferencia de rendimiento (963,0 contra 995,1 req/s, +3 %); el P50 bajó (81 → 59 ms) y el P95 subió (240 → 320 ms). Con 3 instancias el contenedor de Locust usó 88 % de un núcleo, así que el generador de carga pudo estar limitando el resultado. Con esta prueba no se puede afirmar una mejora de 1 a 3 instancias; los datos históricos de F5 (383 → 884 req/s) venían de una instancia que ya devolvía 504.
3. **Punto de quiebre de WH-002: entre 100 y 500 usuarios.** Con 100 usuarios todo funciona (0 fallos). Con 500, 800 y más la corrida arranca bien (~1500 req/s durante unos 20 s) y después colapsa:
   - Entre los 30 y los 60 s las tres réplicas dejan de responder (req/s cae a ≈0) y luego nginx devuelve 502 a casi todo.
   - **Registro de nginx**, en este orden: `upstream timed out (110) while reading response header` → `upstream server temporarily disabled` → `no live upstreams while connecting to upstream`. Con `max_fails=1 fail_timeout=10s`, un solo timeout saca una réplica del pool y, al caer las tres, todo da 502.
   - **Base de datos al terminar:** 120 conexiones de WH-002 en estado `idle in transaction` (3 réplicas × `DB_POOL_SIZE` 20 + `DB_MAX_OVERFLOW` 20) y la API responde `QueuePool limit of size 20 overflow 20 reached, connection timed out, timeout 30.00`. Las réplicas no se recuperan solas: `/health` seguía sin responder minutos después de terminar la carga y docker las marcaba `unhealthy`.
   - Es el atasco que el comentario de `services/warehouse-api/database.py` describe (J-06): los requests esperan una conexión y ocupan los hilos que haría falta para liberarla. Esta prueba lo reproduce bajo sobrecarga con tres réplicas. **No está corregido en este PR.**
4. **Multibodega 50/800/20.** WH-001 y WH-003 no se ven afectadas por el colapso de WH-002 (0 fallos, P95 100 ms y 30 ms): confirma el aislamiento de F4 bajo carga.
5. **Locust.** CPU del contenedor a mitad de la corrida: entre 0,5 % y 88 % en las corridas de un proceso, y 386 % en la de 5000 usuarios, que usa 4 procesos. Solo la corrida de 3 instancias estuvo cerca de saturar un núcleo (ver punto 2). Los valores de 0,5 % y 0,8 % en `rampa-500` y `rampa-1000` no se investigaron; coinciden con el tramo del colapso, en que casi no había tráfico útil.

## Corridas descartadas

La primera tanda lanzó los escenarios de WH-002 uno tras otro sin reiniciar las réplicas: el atasco de un escenario se arrastraba al siguiente y las corridas medían el atasco. Se conservan en [sin-reinicio-entre-escenarios/](sin-reinicio-entre-escenarios/) como evidencia del problema; los resultados válidos son los de la tabla de arriba, con las réplicas de WH-002 y nginx recreados antes de cada escenario.

En esa primera tanda, con PostgreSQL de WH-002 en su valor por defecto (`max_connections=100`) también aparecieron errores `sorry, too many clients already`: 3 réplicas pueden abrir hasta 120 conexiones. Por eso `compose.load.yml` sube `max_connections` a 200 para las pruebas; no evitó el atasco.

## Seguir una transferencia por `correlation_id`

[`traza-correlation-id.txt`](traza-correlation-id.txt): una transferencia WH-001 → WH-002 enviada con `X-Correlation-ID: COR-J09-DEMO` y todas las líneas de log de los servicios que la atendieron.

## Capturas

`<escenario>/grafana-{apis,redis,rabbitmq,workers,saga}.png`: los dashboards de S-07 a mitad de cada corrida, con la ventana de los últimos 3 minutos. Las capturas salen de Chrome headless contra Grafana con acceso anónimo de solo lectura, activado solo en `compose.load.yml`.

## Límites

- Todo corrió en una laptop con Docker: Locust, las APIs, las bases y Grafana comparten CPU y memoria.
- Una sola corrida de 90 s por escenario: no hay repetición ni intervalos de confianza.
- No se repitió la rampa de 5000 usuarios con Locust distribuido en la EC2.
