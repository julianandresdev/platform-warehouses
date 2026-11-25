# Fase 9 — Lambda `report-validator`

## Avance S-08 — Lambda con trigger de S3

La función `services/lambda/report_validator/handler.py` (Python 3.12) se ejecuta cuando se crea un `reports/**/*.json` en el bucket. Por cada objeto:

1. Lo lee y calcula su **tamaño** y su **SHA-256**.
2. **Valida** los campos obligatorios y cuenta sus **registros**.
3. Escribe el resultado en `metadata/<llave original>` (fuera de `reports/`, para que la Lambda no se dispare a sí misma), con el metadato `correlation-id` del objeto.
4. Lo registra en la central con `POST /internal/reports` y `X-API-Key`. Los inválidos se registran con estado `INVALID`.
5. Escribe en el log una línea JSON con el `correlation-id` del metadato del objeto.

La decisión de dejarla fuera de la VPC está en [ADR-0017](../adr/0017-lambda-fuera-de-la-vpc.md).

### Qué se valida

- **`reports/daily/<fecha>/summary.json`** (lo escribe el batch, J-08): debe traer `report_date`, `status`, `missing_warehouses`, `warehouses`, `movements_by_type_and_warehouse`, `net_change_by_sku` y `top_5_skus`; `status` debe ser `SUCCEEDED` o `PARTIAL`; `report_date` debe ser una fecha válida e igual a la de la llave. Los registros son los movimientos leídos de las bodegas (suma de `warehouses[*].movements`).
- **Otro objeto bajo `reports/`:** solo se exige que sea un objeto JSON. Su número de registros queda sin calcular (`null`), porque su formato no está definido todavía.

### Contrato con la central

`POST /internal/reports`, con `X-API-Key` y `X-Correlation-ID`:

```json
{
  "object_key": "reports/daily/2026-11-25/summary.json",
  "status": "VALID",
  "size": 888,
  "checksum": "<sha256>",
  "metadata": {"record_count": 35, "reason": null, "correlation_id": "COR-...", "metadata_key": "metadata/reports/daily/2026-11-25/summary.json"}
}
```

Los cuatro primeros campos corresponden a las columnas `object_key`, `status`, `size` y `checksum` de la tabla `reports` del esquema central; el resto va en su columna `metadata`. Una respuesta 409 se toma como "ya registrado" (repetir el batch de un día vuelve a subir la misma llave).

### Variables de entorno

`CENTRAL_API_URL` y `CENTRAL_API_KEY` (obligatorias) y `S3_ENDPOINT_URL` (solo para probar con MinIO).

### Evidencia

Pruebas: `tests/unit/test_report_validator.py` (23) y, contra MinIO, `tests/integration/test_report_validator_minio.py` (3). Esta última sube un reporte, arma un evento S3 y llama a `lambda_handler` con una central HTTP local.

Línea de log de la Lambda en esa prueba (el `correlation_id` sale del metadato del objeto):

```json
{"event": "report_validated", "correlation_id": "COR-20010101-s08test", "bucket": "warehouse-platform", "object_key": "reports/daily/2001-01-01/summary.json", "status": "VALID", "reason": null, "size": 275, "sha256": "ac6cd9e5...b231b4", "record_count": 5, "metadata_key": "metadata/reports/daily/2001-01-01/summary.json"}
```

### Pendiente

- **Criterio de aceptación en AWS:** subir un reporte a S3 real y ver el metadato, el registro en la central y el log en CloudWatch con el correlation ID. No se hizo: requiere el Learner Lab y la central desplegada.
- **`POST /internal/reports` no existe en la central** de `main` (solo está `POST /internal/batch-runs`) y ningún issue abierto lo asigna. El contrato de arriba sale de la tabla `reports`; hay que acordarlo con quien implemente el endpoint.
- **Tabla Worker / Batch / Lambda con datos propios** (arranque en frío de CloudWatch, duración, costo): requiere mediciones en AWS.
- **Variables de entorno en Terraform:** el módulo `lambda` (S-06) hoy solo pasa `EVENT_BUS_NAME`; falta pasar `CENTRAL_API_URL` y `CENTRAL_API_KEY` cuando se despliegue.
