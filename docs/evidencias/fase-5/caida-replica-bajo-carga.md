# Fase 5 — Caída de una réplica de WH-002 bajo carga

El 26 de noviembre se compiló la API desde el commit `ba67863`, el primer
commit de este PR. Ese commit solo añade documentación sobre `main`, por lo
que el código de la API y la configuración de nginx son los de `main`. Se
levantaron tres réplicas saludables con el Compose distribuido en un
proyecto aislado. Se utilizó el nginx del repositorio, con la API en
`127.0.0.1:8080`.

Ocho clientes concurrentes enviaron solicitudes autenticadas de
`GET /products` durante 25 segundos, con 50 ms de pausa por cliente
entre solicitudes. Tras cinco segundos se inició el apagado inmediato
de `s04-cierre-wh002_api-2`, sin detener la carga.

| Tramo, según el inicio de la solicitud | HTTP 200 | Otros HTTP o errores de red |
| --- | ---: | ---: |
| Antes del apagado | 559 | 0 |
| Desde el inicio del apagado | 2.411 | 0 |

El registro de nginx muestra ambas líneas para la conexión `*610`
a `192.168.32.5:8000`, IP de la réplica apagada:

```text
2026/11/26 14:27:42 [error] 35#35: *610 connect() failed (111: Connection refused) while connecting to upstream
2026/11/26 14:27:42 [warn] 35#35: *610 upstream server temporarily disabled while connecting to upstream
```

La corrida verifica continuidad bajo esa carga y retirada temporal de
la réplica. La tolerancia a timeouts bajo sobrecarga se evalúa por
separado en el [diagnóstico de WH-002](../fase-11/atasco-sobrecarga.md).

## Cómo repetirla

El script [`tests/load/caida_replica.py`](../../../tests/load/caida_replica.py)
implementa el procedimiento descrito arriba (8 clientes, 25 s, 50 ms de
pausa, apagado a los 5 s con `docker kill`) y clasifica cada solicitud por
el instante en que se inició. Se escribió al revisar este PR a partir de
esa descripción: la tabla de arriba procede de la corrida del 26 de
noviembre, no de una ejecución de este script. Al repetirla, los totales
variarán, pero el resultado esperado es cero respuestas distintas de 200
desde el apagado.

```bash
docker compose -p s04-cierre -f infrastructure/compose/compose.distributed.yml \
  up -d --build --scale wh002_api=3
python tests/load/caida_replica.py s04-cierre-wh002_api-2
docker compose -p s04-cierre -f infrastructure/compose/compose.distributed.yml \
  logs nginx | grep -E "Connection refused|temporarily disabled"
```

La clave se toma de `API_KEY` (por defecto `dev-api-key`). Los registros
de nginx mostrarán la IP de la réplica apagada.
