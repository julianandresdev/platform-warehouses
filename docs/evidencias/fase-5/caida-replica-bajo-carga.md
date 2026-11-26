# Fase 5 — Caída de una réplica de WH-002 bajo carga

El 26 de noviembre se compiló la API desde el commit `ba67863` y se
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
