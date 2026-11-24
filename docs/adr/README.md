# Architecture Decision Records

Un ADR por cada decisión que tuvo alternativas. Formato del enunciado: contexto, alternativas, decisión, consecuencias.

Nombre de archivo: `NNNN-titulo-corto.md`.

La plantilla la agrega Esteban (E-01).

| ADR | Título | Autor |
| --- | --- | --- |
| [0001](0001-fastapi-como-framework.md) | FastAPI como framework de la API de bodega | Julian |
| [0003](0003-schema-sql-como-fuente-de-verdad.md) | `schema.sql` como fuente de verdad del esquema, con reglas en la base | Julian |
| [0004](0004-control-de-concurrencia-en-movimientos.md) | Control de concurrencia en los movimientos de inventario | Julian |
| [0005](0005-topologia-rabbitmq.md) | Topología de RabbitMQ y entrega confirmada | David |
| [0006](0006-patron-outbox.md) | Publicación de eventos con outbox transaccional | David |
| [0008](0008-cache-aside-con-redis.md) | Cache Aside con Redis e invalidación síncrona | Julian |
| [0014](0014-idempotencia-comandos-bodega.md) | Idempotencia de los comandos de la Saga en la bodega | Julian |
