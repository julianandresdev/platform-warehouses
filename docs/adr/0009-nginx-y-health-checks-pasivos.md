# ADR-0009 — Nginx y detección pasiva de fallos

## Estado

Implementado en Docker Compose. Pendiente de revisión de Santiago.

## Contexto

WH-002 necesita distribuir las solicitudes entre varias réplicas de API.
El cliente requiere un punto de entrada estable durante cambios de escala
o fallos en una réplica.

## Alternativas consideradas

Exponer las réplicas al cliente le permite escoger instancia, a costa de
repetir la lógica de descubrimiento y manejo de errores en cada cliente.
Un balanceador centraliza esa política. Los chequeos activos pueden
detectar fallos antes de una solicitud, con sondeos adicionales.

## Decisión

Usar Nginx con un grupo de servidores para WH-002 y resolución dinámica
por DNS interno de Docker. La detección pasiva usa `max_fails=1` y
`fail_timeout=10s`. La configuración limita a tres los intentos ante
errores, timeouts y respuestas 502, 503 o 504, según las reglas de Nginx.

## Consecuencias

El cliente usa un solo endpoint y las réplicas comparten PostgreSQL y
Redis de WH-002. Un fallo pasivo se detecta durante tráfico real y una
solicitud puede experimentar demora. Nginx y PostgreSQL también pueden
limitar la disponibilidad o capacidad del conjunto.

## Validación

En un ensayo local se detuvo una de tres réplicas y las 20 solicitudes
a `/health` tuvieron éxito. En el escenario de carga de F5 se observaron
382,98 solicitudes por segundo con una réplica y 884,36 con tres.

Ver la [configuración de Nginx](../../infrastructure/compose/nginx/nginx.conf),
la [prueba de fallo](../evidencias/fase-5/tolerancia-fallos.txt) y la
[comparación de carga](../evidencias/fase-5/comparacion-rendimiento.md).
