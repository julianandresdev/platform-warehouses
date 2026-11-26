# ADR-0014 — Exportación CSV y manifiesto en S3 para AWS Batch

**Estado: propuesta pendiente de aprobación del equipo.**

## Contexto
El issue #12 solicita consumo de APIs de bodega, MinIO/S3 por `common/storage.py`, reportes con rutas específicas y seguimiento central de ejecuciones. La implementación de la rama actual usa consultas locales PostgreSQL para exportar CSV a S3 y un manifiesto SHA-256, procesado con AWS Batch Fargate.

## Alternativas
1. Contrato del issue #12: APIs HTTP por bodega, reportes compatibles y estados `PARTIAL`.
2. Exportación local CSV y manifiesto en S3 (implementación existente).

## Decisión propuesta
Conservar temporalmente el flujo CSV para la demostración AWS Batch **sin considerarlo sustituto del contrato #12**. Integrar las APIs y el registro central antes de cerrar el issue, salvo aceptación formal de Julian y el equipo para cambiar el alcance.

## Consecuencias
Ventajas: integridad por SHA-256 y ejecución Fargate probada. Riesgos: exportación acoplada a Postgres local, ausencia de `PARTIAL`, rutas incompatibles y diferencias en semántica del registro de ejecuciones. La programación diaria permanece deshabilitada.
