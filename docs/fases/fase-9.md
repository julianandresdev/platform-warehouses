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

### Prueba en AWS (S-09, 26 nov 2026)

Con el despliegue de [aws.md](../aws.md): el batch subió `reports/daily/2026-11-26/summary.json` al bucket real con `correlation-id: COR-20261126-e8ddb6c4`; la Lambda escribió `metadata/reports/daily/2026-11-26/summary.json` (`VALID`, 33 registros, SHA-256), registró el reporte en la central con `POST /internal/reports` y dejó en CloudWatch el log `report_validated` con el mismo `correlation_id`. Evidencia: [`s3.txt`](../evidencias/fase-9/s3.txt), [`cloudwatch-lambda.txt`](../evidencias/fase-9/cloudwatch-lambda.txt) y [`lambda.txt`](../evidencias/fase-9/lambda.txt). Cerrar el criterio dependía del endpoint de la central, que llega con #73.

### Worker, Batch y Lambda con datos propios

| | Worker | Batch | Lambda |
| --- | --- | --- | --- |
| Qué lo dispara | Un mensaje en RabbitMQ (continuo) | Una ejecución manual o programada del reporte diario | Crear un objeto `reports/*.json` en S3 |
| Estado entre usos | Siempre encendido (contenedor de la EC2) | Proceso nuevo en cada corrida | Se apaga solo; la primera invocación arranca en frío |
| Arranque | Ninguno | Arranque del proceso | Frío: 329 ms de inicialización; caliente: ninguna |
| Duración medida | Una transferencia completa por la Saga (tres comandos de bodega y los eventos) quedó `COMPLETED` en 4 s o menos | 5,8 s la segunda corrida (3 bodegas por API, 5 objetos a S3 y registro en la central), medida desde la laptop contra la EC2 | 3226 ms en frío (incluye la llamada a la central) y 429 ms en caliente |
| Memoria | No medida en AWS | No medida | 93 MB de 128 MB |
| Costo | Entra en el de la EC2 encendida (≈ USD 0,083 por hora en `t3.large`) | Solo mientras corre | ≈ USD 0,00001 por invocación fría (128 MB, 3,6 s facturados) |

Los números de Lambda salen de las líneas `REPORT` de CloudWatch. El resto son mediciones únicas, sin repetición: sirven de orden de magnitud, no como promedio. El costo es un cálculo con precios de lista, no una medición.

### Pendiente

- **Variables de la Lambda:** ya se pasan desde Terraform (`CENTRAL_API_URL` y `CENTRAL_API_KEY`), con la IP elástica de la EC2.
- El reporte de la prueba es `reports/daily/`; los de `reports/jobs/` (J-08, punto 6) no se probaron en AWS.
- `CENTRAL_API_KEY` va como variable de entorno de la función (visible en la consola de Lambda); es aceptable solo en el laboratorio.
