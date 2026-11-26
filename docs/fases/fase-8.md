# Fase 8 — S3, batch y almacenamiento de objetos

## Avance S-05 — MinIO en Compose y `common/storage.py`

Se añadió el profile `storage` al Compose raíz con `minio` (API en 9000, 9001 publicado) y `minio-init`, que crea el bucket `warehouse-platform` y termina. `services/common/common/storage.py` es un cliente boto3 configurado solo por entorno: `S3_ENDPOINT_URL` (vacío en AWS) y `S3_BUCKET`. Expone `put_json(key, obj, metadata)` y `list(prefix)`. La decisión y sus consecuencias están en [ADR-0011](../adr/0011-minio-local-y-s3-en-aws.md).

```bash
docker compose --profile storage up -d minio minio-init
```

### Estructura del bucket

| Prefijo | Contenido |
| --- | --- |
| `warehouses/` | Fotos de inventario por bodega: `warehouses/WH-00X/YYYY/MM/inventory-YYYY-MM-DD.json` |
| `reports/` | Reportes generados: `reports/daily/YYYY-MM-DD/summary.json` y los trabajos de reportes |
| `metadata/` | Metadatos de los reportes (fuera de `reports/` para no disparar el trigger de la Lambda en bucle) |
| `audit/` | Eventos de auditoría |
| `exports/` | Exportaciones |

Los prefijos `warehouses/`, `reports/` y `metadata/` son los que nombran los issues #12 y #29; `audit/` y `exports/` los lista el issue #26 sin más detalle.

### Evidencia

- `tests/integration/test_storage.py`: **3 pruebas pasadas** contra MinIO (escribir y leer un objeto con metadato `correlation-id`, reemplazo de la misma llave y listado por prefijo). Sin `S3_ENDPOINT_URL` se omiten.
- `minio-init` termina con código 0 y se puede repetir sin error (`--ignore-existing`).
- `mc ls local` dentro de la red de Compose:

  ```text
  [2026-11-25 18:55:03 UTC]     0B warehouse-platform/
  ```

- `GET http://localhost:9000/minio/health/live` responde 200.
- La consola web no responde en el puerto 9001 con esta versión de MinIO (se comprobó dentro del contenedor).

## Avance J-08 — Reporte diario del batch

El batch es un trabajo que corre una vez y termina, fuera de cualquier request. Lee cada bodega **por su API** (no por su base), escribe los resultados en el bucket y registra la ejecución en la central. La decisión está en [ADR-0014](../adr/0014-batch-lee-bodegas-por-api.md).

- **Bodega:** `GET /inventory` (foto) y `GET /movements?from=&to=&page=&page_size=`, de solo lectura y con `X-API-Key`.
- **Batch:** `python -m batch.daily_report --date YYYY-MM-DD` (por defecto, ayer en UTC), servicio `batch` del profile `storage` con `restart: "no"`.
- **Salida:** `warehouses/WH-00X/YYYY/MM/inventory-YYYY-MM-DD.json` y `reports/daily/YYYY-MM-DD/summary.json`, ambos con el metadato `correlation-id`.
- **Central:** `POST /internal/batch-runs` con `run_id`, `report_date`, `status`, `started_at`, `finished_at` y `objects`.

```bash
# Con las tres bodegas de compose.distributed.yml arriba (WH-002 por nginx, en 8080):
docker compose --profile storage up -d central-api minio minio-init
docker compose --profile storage run --rm --no-deps \
  -e WH001_API_URL=http://host.docker.internal:8101 \
  -e WH002_API_URL=http://host.docker.internal:8080 \
  -e WH003_API_URL=http://host.docker.internal:8103 \
  batch python -m batch.daily_report --date 2026-11-25
```

El Compose raíz solo tiene la bodega WH-001; mientras `WH002_API_URL` y `WH003_API_URL` no estén configuradas, esas bodegas cuentan como faltantes y el reporte sale `PARTIAL`.

### Evidencia

Pruebas: `tests/unit/test_daily_report.py` (12) y `tests/integration/fase1/test_batch_read_endpoints.py` (13, contando los parámetros) pasan; el CI las ejecuta.

**Criterio 1 — dos ejecuciones de la misma fecha:** mismos objetos y dos filas en `batch_runs`.

```text
$ mc ls --recursive local/warehouse-platform
[2026-11-25 19:01:56 UTC]   888B STANDARD reports/daily/2026-11-25/summary.json
[2026-11-25 19:01:56 UTC] 2.0KiB STANDARD warehouses/WH-001/2026/11/inventory-2026-11-25.json
[2026-11-25 19:01:56 UTC] 2.0KiB STANDARD warehouses/WH-002/2026/11/inventory-2026-11-25.json
[2026-11-25 19:01:56 UTC] 2.0KiB STANDARD warehouses/WH-003/2026/11/inventory-2026-11-25.json

$ mc stat local/warehouse-platform/reports/daily/2026-11-25/summary.json
Metadata  :
  X-Amz-Meta-Correlation-Id: COR-20261125-5e8623dc

central=# SELECT run_id, report_date, status, jsonb_array_length(objects) AS objetos FROM batch_runs;
                run_id                | report_date |  status   | objetos
--------------------------------------+-------------+-----------+---------
 3e442227-b40a-4524-b1a8-83977f719233 | 2026-11-25  | SUCCEEDED |       4
 8758fc09-a4ff-487e-8306-5af1c421ba03 | 2026-11-25  | SUCCEEDED |       4
```

**Criterio 2 — una bodega caída:** con `wh002_api` detenida, el batch deja `PARTIAL`, no escribe la foto de WH-002 y registra la ejecución.

```text
{"level": "ERROR", "event": "warehouse_unavailable", "error": "HTTP Error 504: Gateway Time-out"}
status= PARTIAL missing= ['WH-002'] WH-002= {'status': 'MISSING'}

 report_date |  status   | objetos
-------------+-----------+---------
 2026-11-25  | PARTIAL   |       3
```

**Ejemplo de `reports/daily/2026-11-25/summary.json`** (abreviado):

```json
{
  "report_date": "2026-11-25",
  "status": "SUCCEEDED",
  "missing_warehouses": [],
  "movements_by_type_and_warehouse": {
    "WH-001": {"RECEIPT": 11, "SHIPMENT": 1},
    "WH-002": {"RECEIPT": 11},
    "WH-003": {"RECEIPT": 11, "SHIPMENT": 1}
  },
  "net_change_by_sku": {"P-001": 192, "P-002": 260, "...": "..."},
  "top_5_skus": [
    {"sku": "P-004", "units_moved": 340, "movements": 3},
    {"sku": "P-007", "units_moved": 325, "movements": 3}
  ],
  "warehouses": {"WH-001": {"status": "OK", "inventory_rows": 10, "movements": 12}}
}
```

### Preguntas del profesor

Las cuatro preguntas de diseño y sus respuestas base se tomaron de `docs/fases/fase-8.md` del PR #52; hay que confirmar que son las del enunciado.

**¿Por qué procesar fuera del request?** Para no bloquear las operaciones de inventario con reportes grandes y para poder reintentar: el batch es una ejecución aparte, y repetir un día reemplaza los mismos objetos.

**¿Cuándo usar Batch?** En agregaciones periódicas y cargas por lotes, como este reporte diario.

**¿Cuándo usar un worker?** En el procesamiento continuo de mensajes.

**¿Cuándo usar Lambda?** En validaciones cortas disparadas por eventos.

### Punto 6 — resultado de `POST /reports` en `reports/jobs/<job_id>.json`

Con D-04 en `main` (#66), el worker de reportes de cada bodega escribe el resultado también en el bucket, con `common/storage.py` y el metadato `correlation-id` del evento `REPORT_REQUESTED`. Se activa con `REPORTS_TO_S3=true` (por defecto está apagado, así que `docker compose up` sin el profile `storage` no cambia). La fila de `report_jobs` conserva `status` y `result`, y `result` añade `object_key`; así `GET /reports/jobs/{id}` sigue respondiendo igual que en D-04. Si la escritura en el bucket falla, el trabajo queda `FAILED` con el error.

```bash
REPORTS_TO_S3=true docker compose --profile storage up -d db rabbitmq rabbitmq-topology api reports-worker outbox-worker minio minio-init
curl -X POST localhost:8000/reports -H "X-API-Key: $API_KEY" -H 'Content-Type: application/json' \
  -H 'X-Correlation-ID: COR-J08-PT6' -d '{"start_at":"2026-11-01T00:00:00Z","end_at":"2026-12-01T00:00:00Z"}'
```

```text
$ mc ls local/warehouse-platform/reports/jobs/
[2026-11-26 03:54:47 UTC]   859B STANDARD a4a7165a-7e23-4cdb-807d-9db525b4c2b9.json

$ mc stat ... a4a7165a-7e23-4cdb-807d-9db525b4c2b9.json
  X-Amz-Meta-Correlation-Id: COR-J08-PT6

GET /reports/jobs/a4a7165a-...  ->  DONE  result.object_key = reports/jobs/a4a7165a-7e23-4cdb-807d-9db525b4c2b9.json
```

Pruebas: `tests/unit/test_report_job_storage.py` (3): llave, metadato y reemplazo al repetir el mismo trabajo.

### Pendiente

- El cambio neto por SKU no conoce los tipos de movimiento de la Saga (`RESERVATION`, `TRANSFER_*`); ver las consecuencias del ADR-0014.
- Los reportes de `reports/jobs/` los valida la Lambda solo como objeto JSON; su formato no tiene esquema propio.
