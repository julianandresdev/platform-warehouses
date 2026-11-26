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
