# Evidencia de la fase 9 — Lambda y EventBridge

## Validación realizada en AWS Academy

- Lambda `warehouse-platform-export-handler` (Python 3.12) valida JSON en S3 bajo `exports/`.
- Prueba de JSON válido: `processed=1`, `rejected=0`.
- Prueba de JSON inválido: `processed=0`, `rejected=1`.
- El 24 de noviembre de 2026 se copió `exports/phase9-integracion-final.json` en S3; Lambda se invocó automáticamente, validó el reporte y publicó `InventoryReportCreated` en EventBridge.
- La regla `warehouse-platform-report-created`, su política y el destino CloudWatch están declarados en `infrastructure/terraform/eventbridge.tf`.
- EventBridge registró el evento `4ed450c0-2e89-9649-7098-818ec3fa9c8b` en `/aws/events/warehouse-platform-report-created`, con la misma clave de objeto; así se verificó **S3 → Lambda → EventBridge → CloudWatch**.
- Evidencias reales: `evidencias/fase-9/lambda-integracion-final.txt` y `evidencias/fase-9/eventbridge-integracion-final.txt`.
- Cinco pruebas unitarias de la versión original fueron ejecutadas satisfactoriamente, según la revisión del PR.

## Diferencias frente al contrato del issue #29

Se agregó código para metadata en `metadata/reports/...`, `POST /internal/reports` con `X-API-Key` y logging de `correlation-id`. Su funcionamiento con la API central, MinIO y la comparación cuantitativa Worker/Batch/Lambda **no está verificado**. Tampoco se ha migrado el trigger de `exports/` a `reports/`. **No marcar el issue #29 como cerrado hasta implementar y validar estos contratos o lograr aceptación explícita del cambio de diseño.**

Consultar `docs/adr/0017-lambda-validacion-eventos.md` para la decisión propuesta y sus limitaciones.
