# ADR-0002: Una imagen por dominio, con varios comandos

- Estado: aceptado
- Fecha: 2026-11-22
- Autor: Julian

## Contexto

El proyecto tiene tres bodegas (WH-001, WH-002 y WH-003) y, además de la API de cada una, procesos de fondo: relay del outbox, consumidor de comandos de transferencia, invalidación de caché y reportes. También habrá una central con su API y sus workers. Hay que decidir cuántas imágenes se construyen y cómo se reparte el código compartido (sobre de eventos, correlation ID, logs, cliente de RabbitMQ).

## Alternativas

| Alternativa | A favor | En contra |
| --- | --- | --- |
| **Una imagen por dominio (`warehouse`, `central`), con varios comandos** | Las tres bodegas son la misma imagen con otro `WAREHOUSE_ID`; la API y sus workers comparten modelos y reglas de negocio; menos builds | La imagen incluye código que un proceso concreto no usa |
| Una imagen por proceso (api, relay, worker, ...) | Imágenes mínimas | Modelos y reglas duplicados o publicados como librería; builds y versiones por multiplicar |
| Una imagen por bodega | Aislamiento total | Tres códigos que mantener: justo lo que se quiere evitar |
| Un monolito con todo el proyecto | Un solo build | La central y la bodega quedan acopladas; no se puede escalar cada dominio por separado |

## Decisión

- Una imagen por dominio. `warehouse-api` se levanta una vez por bodega, configurada solo por variables de entorno (`WAREHOUSE_ID`, `DATABASE_URL`, `API_KEY`, y después `REDIS_URL` y `RABBITMQ_URL`). Los workers de la bodega usarán la misma imagen con otro comando.
- El código compartido vive en `services/common/`, un paquete instalable (`warehouse-common`). Cada imagen lo instala con `pip install ./common`.
- Por eso el contexto de build es `services/`, y el Dockerfile se invoca con `-f warehouse-api/Dockerfile`.

## Consecuencias

- Agregar una bodega es agregar servicios y variables en el compose, no código ni imágenes nuevas.
- Un cambio en `services/common/` obliga a reconstruir las imágenes que lo usan.
- Cada servicio nuevo (`central`, `batch`, `lambda`) decide su propia imagen; si necesita `common`, usa el mismo contexto `services/`.
- La imagen de la bodega crece con las dependencias de sus workers (aio-pika, por ejemplo); se acepta a cambio de no duplicar el dominio.
