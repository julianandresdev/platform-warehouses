# Fase 5 - Load Balancing y escalamiento

Líder: Santiago · Apoyo: Esteban

## Qué se construyó

Nginx enruta solicitudes a las réplicas de WH-002 y vuelve a resolver su
nombre con el DNS interno de Docker al escalar. La configuración en
`main` usa el puerto 8080, `max_fails=1`, `fail_timeout=10s` y hasta
tres intentos de upstream.

## Revisión de S-04

La [prueba inicial](../evidencias/fase-5/tolerancia-fallos.txt) registró
20 de 20 respuestas de `GET /health` con una réplica apagada. La
[prueba de caída bajo carga](../evidencias/fase-5/caida-replica-bajo-carga.md)
extendió la verificación a `GET /products`. Se registraron 2.411
respuestas HTTP 200 desde el inicio del apagado, sin errores para el
cliente, y nginx dejó constancia de la retirada temporal de la réplica.

El issue #25 especifica puerto 8002, `max_fails=2`, dos intentos,
`proxy_connect_timeout=1s`, `X-Upstream`, `X-Instance` y logs JSON
con datos del upstream. La configuración actual usa tres segundos
para conectar y carece de ese encabezado upstream y del formato JSON.
Queda por conciliar esas diferencias y comprobar el encabezado y el
estado `unhealthy` de cada réplica.

La [prueba J-09](../evidencias/fase-11/README.md) registró que nginx
expulsaba las tres réplicas tras timeouts bajo carga. Para cerrar #25,
hay que medir un umbral de detección que tolere timeouts aislados y
conserve el failover durante una caída real.

## Evidencia

- [Comparación histórica de una y tres réplicas](../evidencias/fase-5/comparacion-rendimiento.md).
- [Diagnóstico de sobrecarga y recuperación de WH-002](../evidencias/fase-11/atasco-sobrecarga.md).
- [ADR-0009 sobre Nginx y health checks pasivos](../adr/0009-nginx-y-health-checks-pasivos.md).
