# Fase 5 - Load Balancing y escalamiento

Líder: Santiago · Apoyo: Esteban

## Qué se construyó

Nginx enruta solicitudes a las réplicas de WH-002 y vuelve a resolver su
nombre con el DNS interno de Docker al escalar. La configuración por
defecto (`nginx.conf`, puerto 8080) usa `max_fails=1`, `fail_timeout=10s`
y hasta tres intentos de upstream; sigue igual y la usan la demo y la F11.

S-04 añade el perfil `lb` de [`compose.distributed.yml`](../../infrastructure/compose/compose.distributed.yml),
que cumple la especificación del issue #25 sin tocar lo anterior:

- **Tres réplicas** `wh002_api_1/2/3` (mismo anchor `x-api`, misma base y Redis de WH-002, `hostname` fijo `wh002-api-N`) y un nginx `wh002_lb` en el puerto **8002** (`WH002_LB_PORT`). Son servicios nuevos: la `wh002_api` original no publica puerto en el host, así que no hay choque con el 8002. Con el perfil `lb` conviven el nginx de siempre (8080, sobre `wh002_api`) y el nuevo (8002, sobre las tres réplicas).
- **[`nginx.lb.conf`](../../infrastructure/compose/nginx/nginx.lb.conf)**: round robin, `max_fails=2 fail_timeout=10s`, `proxy_next_upstream error timeout http_502 http_503`, `proxy_next_upstream_tries 2`, `proxy_connect_timeout 1s`, header `X-Upstream: $upstream_addr` y log de acceso en JSON con `upstream_addr`, `upstream_status` y `request_time`.
- **La API responde `X-Instance: <HOSTNAME>`** con un middleware ASGI (`common/instance.py`) y su prueba unitaria (`tests/unit/test_instance_header.py`).
- **Healthcheck de Docker** sobre `/health` en cada réplica (ya definido en el anchor `x-api`).

Cómo usarlo:

```sh
make up STACK=multi PROFILES=lb          # o: docker compose -f infrastructure/compose/compose.distributed.yml --profile lb up -d --build
curl -si -H 'X-API-Key: dev-api-key' localhost:8002/inventory/P-001 | grep -i '^x-'
docker compose -f infrastructure/compose/compose.distributed.yml --profile lb stop wh002_api_2   # caída de una réplica
docker compose -f infrastructure/compose/compose.distributed.yml --profile lb logs wh002_lb      # log JSON de nginx
```

Para el experimento «1 contra 3 instancias» sin la `wh002_api` original basta no usarla: el tráfico del 8002 solo pasa por las réplicas numeradas.

## Cierre de la fase

Evidencia generada con el perfil `lb` en un proyecto aislado (nginx publicado en el 28202 por tener el 8002 ocupado en la máquina de pruebas):

- **Reparto**: 9 peticiones seguidas devolvieron `X-Instance` `wh002-api-3, 1, 2, 3, 1, 2, 3, 1, 2` y `X-Upstream` con la IP de cada réplica ([`s04-lb-experimento.txt`](../evidencias/fase-5/s04-lb-experimento.txt)).
- **Caída en plena carga**: se detuvo `wh002_api_2` con 40 peticiones en curso (una cada 250 ms): **40 de 40 HTTP 200**. Dos peticiones tardaron ~1 s (`request_time` 1.005): `upstream_addr":"…4:8000, …5:8000"` y `upstream_status":"504, 200"` en el log JSON, es decir, nginx intentó la réplica caída, venció `proxy_connect_timeout 1s` y reintentó en otra. Después de dos fallos (`max_fails=2`) nginx dejó de enviarle tráfico: las 9 peticiones siguientes alternaron solo `wh002-api-3` y `wh002-api-1`, sin demora. Al reiniciarla volvió al reparto.
- **`unhealthy`**: con `docker kill --signal=STOP` sobre `wh002_api_3` (el proceso deja de contestar), `docker compose ps` la marcó `unhealthy` en unos 60 s y volvió a `healthy` tras `CONT` ([`s04-healthcheck-unhealthy.txt`](../evidencias/fase-5/s04-healthcheck-unhealthy.txt)).
- Pruebas anteriores que siguen vigentes: [20 de 20 `/health` con una réplica apagada](../evidencias/fase-5/tolerancia-fallos.txt), [2.411 respuestas 200 sin errores en la caída bajo carga](../evidencias/fase-5/caida-replica-bajo-carga.md) y la [comparación de rendimiento](../evidencias/fase-5/comparacion-rendimiento.md): 382,98 req/s con una réplica frente a 884,36 con tres, y 500 respuestas 504 con una réplica frente a ninguna con tres.

Límite conocido (J-09): bajo sobrecarga (≥500 usuarios) los timeouts de lectura pueden sacar las tres réplicas del pool por marcado pasivo y nginx devuelve 502 ([evidencia F11](../evidencias/fase-11/README.md)). El valor `max_fails=2` del issue es más tolerante que el `max_fails=1` del nginx por defecto, pero no elimina el riesgo; esa corrida con carga alta no se repitió con `nginx.lb.conf`.

## Decisiones

| Decisión | Elegido | Por qué |
| --- | --- | --- |
| Balanceador | nginx ([ADR-0009](../adr/0009-nginx-y-health-checks-pasivos.md)) | Un solo contenedor, sin coste extra, suficiente para 3 réplicas locales |
| Algoritmo | Round robin | Las réplicas son idénticas y sin estado; el reparto es uniforme y fácil de verificar con `X-Instance` |
| Detección de fallos | Pasiva: `max_fails=2 fail_timeout=10s` | Detecta con tráfico real y sin sondeos; tolera un fallo aislado |
| Reintentos | `proxy_next_upstream error timeout http_502 http_503`, 2 intentos | Un cliente no ve la caída de una réplica; no se reintenta en 504 ni se repite un POST (nginx no reintenta métodos no idempotentes) |
| Conexión | `proxy_connect_timeout 1s` | Una réplica caída cuesta como máximo 1 s a la petición que la descubre |
| Perfil `lb` aparte del nginx por defecto | `nginx.lb.conf` + `wh002_lb` en el 8002 | No cambia la demo ni la F11 (8080); el experimento del issue queda reproducible |
| Observabilidad del reparto | `X-Instance` (API) y `X-Upstream` + log JSON (nginx) | Se ve qué réplica atendió y si hubo reintento sin herramientas adicionales |
| Puertos | 8002 con `WH002_LB_PORT` | Es el puerto del issue; el 8080 se conserva para lo existente |

## Preguntas del profesor

**1. ¿Por qué las APIs deben ser stateless para poder balancear?**
Porque el balanceador puede mandar cada petición a cualquier réplica. Si una réplica guardara estado en memoria (sesión, caché local, contadores), la siguiente petición del mismo cliente podría caer en otra réplica y no lo encontraría. Aquí el estado vive fuera de la API: el inventario en el PostgreSQL de la bodega, la caché en su Redis y los eventos en el outbox. La autenticación es una `X-API-Key` en cada petición y no hay sesión. Por eso se pueden añadir o quitar réplicas sin migrar nada, y `X-Instance` muestra que respuestas idénticas salen de instancias distintas.

**2. ¿Qué pasa cuando una instancia muere?**
Las peticiones que ya iban a ella fallan al conectar; con `proxy_next_upstream` nginx las reintenta en otra réplica (hasta 2 intentos) y el cliente recibe 200, con un coste de hasta 1 s (`proxy_connect_timeout`). Tras `max_fails=2` fallos en `fail_timeout=10s`, nginx la saca del pool durante 10 s y luego prueba de nuevo; si ya volvió, se reincorpora sola. En el experimento fueron 40 de 40 respuestas 200 con dos peticiones lentas. Lo que no cubre: las peticiones en vuelo dentro de la réplica que murió a mitad de procesar (nginx puede reintentar un GET, pero no repetirá un POST), y una sobrecarga general, donde los timeouts pueden expulsar a todas las réplicas.

**3. ¿Health checks pasivos o activos?**
Los pasivos (open source de nginx) infieren la salud del tráfico real: no añaden carga ni configuración, pero el primer usuario que toca una réplica caída paga la demora y una réplica que no recibe tráfico no se detecta. Los activos sondean `/health` periódicamente y retiran la réplica antes de que la pruebe un usuario, a costa de sondeos adicionales y de que un `/health` superficial puede decir «sano» con la base caída. En este proyecto hay ambos niveles: nginx es pasivo y Docker hace un chequeo activo de `/health` en cada réplica (`healthy`/`unhealthy` en `docker compose ps`), pero Docker no le avisa a nginx. Los chequeos activos propios de nginx requieren NGINX Plus.

**4. ¿nginx, HAProxy o ALB?** ([ADR-0009](../adr/0009-nginx-y-health-checks-pasivos.md))
nginx: ya conocido, un contenedor, configuración sencilla y suficiente para esta escala. HAProxy tiene chequeos activos y estadísticas por servidor incluidos en la versión libre y una L7 más afinada, a cambio de otra pieza que aprender y operar. El ALB de AWS aporta chequeos activos, multi-AZ y TLS gestionado sin operar nada, pero cuesta dinero y no corre en local ni se puede reproducir en el Learner Lab con la misma configuración. Se eligió nginx para el entorno de desarrollo y la demo; en producción en AWS lo razonable sería un ALB delante de las instancias.

## Evidencia

- [Reparto y caída de una réplica](../evidencias/fase-5/s04-lb-experimento.txt): `X-Instance`, `X-Upstream`, log JSON de nginx con reintento.
- [Réplica `unhealthy`](../evidencias/fase-5/s04-healthcheck-unhealthy.txt).
- [Prueba inicial de tolerancia](../evidencias/fase-5/tolerancia-fallos.txt) y [caída bajo carga](../evidencias/fase-5/caida-replica-bajo-carga.md).
- [Comparación histórica de una y tres réplicas](../evidencias/fase-5/comparacion-rendimiento.md).
- [Diagnóstico de sobrecarga y recuperación de WH-002](../evidencias/fase-11/atasco-sobrecarga.md).
- [ADR-0009 sobre Nginx y health checks pasivos](../adr/0009-nginx-y-health-checks-pasivos.md).
