# Fase 8 — AWS Batch y almacenamiento en S3

## Implementación probada

El flujo existente es PostgreSQL local → exportación CSV → S3 (`inputs/movements/daily/`) → AWS Batch Fargate → reporte JSON (`exports/daily-movements-YYYY-MM-DD.json`) → Lambda. La ejecución AWS Batch revisión 4, trabajo `37371f11-8908-488f-9ef3-d4cf1e2f0129`, terminó `SUCCEEDED` con salida 0 para el 19 de noviembre de 2026. Se verificaron ocho pruebas unitarias.

El manifiesto verifica SHA-256 de los CSV; el registro S3 evita repetir fechas completadas. La programación periódica permanece deshabilitada porque la exportación depende de PostgreSQL local.

## Diferencias frente al issue #12

El issue #12 —asignado a Julian— exige consultas a cada bodega por API, CLI `python -m batch.daily_report`, almacenamiento mediante `common/storage.py`, rutas `warehouses/WH-00X/...` y `reports/daily/YYYY-MM-DD/summary.json`, estado `PARTIAL` para bodega no disponible, registro central `POST /internal/batch-runs` y doble ejecución con dos registros. Se agregó un CLI por API en `services/batch/batch/daily_report.py` y endpoints de solo lectura en `services/warehouse-api/app.py`, pero falta ejecutar pruebas de integración con las tres bodegas, MinIO y la central; no declarar #12 cerrado sin ellas.

## Evidencias y análisis

El detalle de las pruebas y la arquitectura implementada están en `docs/fases/fase-8-entrega.md` y `evidencias/fase-8/`. Ver también la decisión propuesta `docs/adr/0014-batch-csv-s3.md`.

## Respuestas de diseño

**¿Por qué procesar fuera del request?** Para evitar bloquear operaciones de inventario por reportes grandes y facilitar reintentos.

**¿Cuándo Batch?** En agregaciones periódicas y cargas por lotes.

**¿Cuándo worker?** En procesamiento continuo de mensajes.

**¿Cuándo Lambda?** En validaciones cortas activadas por eventos.
