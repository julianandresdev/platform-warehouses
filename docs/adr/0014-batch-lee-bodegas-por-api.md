# ADR-0014: El batch lee las bodegas por API

- Estado: aceptado
- Fecha: 2026-11-25
- Autor: Julian (tarea J-08, issue #12)

## Contexto

El reporte diario no debe correr dentro de un request HTTP y tiene que poder repetirse. Necesita el inventario y los movimientos de las tres bodegas, y cada bodega tiene su propia base de datos (aislamiento de F4). Además, una bodega puede estar caída cuando corra el batch.

## Alternativas

| Alternativa | A favor | En contra |
| --- | --- | --- |
| **Leer cada bodega por su API (`GET /inventory`, `GET /movements`)** | Respeta el aislamiento: el batch no necesita credenciales de las bases; una bodega caída se detecta y se marca; la API ya valida la API key | Los endpoints de lectura son nuevos y pasan por la API |
| Leer directamente las bases de las bodegas | Sin endpoints nuevos | Rompe el aislamiento (el batch conoce tres bases y sus contraseñas); no distingue "bodega caída" de "base caída" con claridad |
| Exportar CSV desde cada base a S3 y procesarlos | Desacopla la lectura del cómputo | Exige un paso previo de exportación que corre dentro de cada bodega y queda fuera del contrato del issue |

## Decisión

- La bodega expone, protegidos por `X-API-Key`, `GET /inventory` (foto de la bodega) y `GET /movements?from=&to=&page=&page_size=` (movimientos con `from <= created_at < to`, paginados, ordenados por `created_at` e `id`). Un instante sin zona horaria se lee como UTC; con zona se convierte a UTC.
- `python -m batch.daily_report --date YYYY-MM-DD` (por defecto, ayer en UTC) lee las tres bodegas. Si una falla se marca como faltante y la ejecución queda `PARTIAL`; el resumen y los demás objetos se escriben igual.
- El día va de 00:00 a 24:00 UTC porque `created_at` se guarda en UTC.
- Las llaves de los objetos dependen solo de la fecha (`warehouses/WH-00X/YYYY/MM/inventory-YYYY-MM-DD.json` y `reports/daily/YYYY-MM-DD/summary.json`), así que repetir un día reemplaza los mismos objetos. Cada ejecución se registra en la central con un `run_id` nuevo, lo que deja una fila por ejecución en `batch_runs`.
- Cada objeto lleva el metadato `correlation-id` de la ejecución, que también viaja en `X-Correlation-ID` hacia las bodegas y la central.

## Consecuencias

- Una bodega caída no impide el reporte de las demás, pero su foto del día no se escribe (queda la del último día en que sí respondió).
- El cambio neto por SKU solo conoce `RECEIPT` (suma), `SHIPMENT` (resta) y `ADJUSTMENT` (suma con signo). Un tipo de movimiento distinto se cuenta en `movements_by_type_and_warehouse` pero no entra en el cambio neto, y se registra una advertencia. Cuando existan nuevos tipos (p. ej. los de la Saga) habrá que decidir su efecto.
- Si la central no registra la ejecución, el batch termina con código 1 después de haber escrito los objetos; repetirlo es seguro.
- La paginación recorre hasta 10 000 páginas de 100 movimientos por bodega.
