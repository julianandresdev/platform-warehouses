# ADR-0011: MinIO en local, S3 en AWS

- Estado: aceptado
- Fecha: 2026-11-25
- Autor: Julian (tarea S-05, issue #26; responsable asignado: Santiago)

## Contexto

El batch (F8), la Lambda (F9) y los reportes necesitan un almacenamiento de objetos. En AWS es S3, pero usar S3 real durante todo el desarrollo gasta presupuesto y sesiones del Learner Lab. Hace falta un S3 local que se levante con Compose y que el mismo código funcione en los dos sitios.

## Alternativas

| Alternativa | A favor | En contra |
| --- | --- | --- |
| **MinIO local + boto3 con `S3_ENDPOINT_URL`** | API S3 real; el código no cambia entre local y AWS; gratis | Hay que mantener un contenedor más; las imágenes oficiales ya no se publican (ver Consecuencias) |
| S3 real también en desarrollo | Cero diferencias con producción | Consume presupuesto y sesiones del lab; no funciona sin conexión |
| Carpeta local con una abstracción propia | Sin contenedores | El código de AWS sería otro y quedaría sin probar; no hay metadatos ni listado por prefijo equivalentes |

## Decisión

- Profile `storage` de Compose con dos servicios: `minio` (puertos 9000 y 9001, volumen `minio_data`, healthcheck en `/minio/health/live`) y `minio-init`, que crea el bucket `warehouse-platform` con `mc mb --ignore-existing` y termina (`restart: "no"`). No arrancan con `docker compose up`; se piden con `--profile storage`.
- `services/common/common/storage.py`, sobre boto3, configurado solo por entorno: `S3_ENDPOINT_URL` (vacío en AWS), `S3_BUCKET` (por defecto `warehouse-platform`) y las variables estándar de AWS. Expone `put_json(key, obj, metadata)` y `list(prefix)`.
- Estructura del bucket: `warehouses/`, `reports/`, `metadata/`, `audit/` y `exports/` (detalle en [fase-8.md](../fases/fase-8.md)).

## Consecuencias

- **Imágenes.** Las imágenes oficiales `minio/minio` y `minio/mc` ya no se pueden descargar: Docker Hub y Quay las retiraron y `dl.min.io` responde 410. Se usan `bitnamilegacy/minio:2025.7.23` y `bitnamilegacy/minio-client:2025.7.21`, con versión fija. Están archivadas y no reciben parches de seguridad, así que solo sirven para desarrollo local. Si se necesita otra imagen, basta cambiar las dos líneas `image:` de Compose.
- **Consola web.** Esta versión de MinIO no sirve la interfaz web en el puerto 9001 (se comprobó dentro del contenedor). El puerto queda publicado como pide el issue; el contenido del bucket se revisa con `mc`.
- Las credenciales de MinIO por defecto (`minioadmin`) son solo para local y se pueden cambiar con `MINIO_ROOT_USER` y `MINIO_ROOT_PASSWORD`.
- `common` ahora depende de `boto3`, así que las imágenes que instalan `common` lo incluyen.
- Escribir dos veces la misma llave reemplaza el objeto, lo que permite reejecutar un trabajo sin duplicar resultados.
