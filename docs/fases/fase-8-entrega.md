# Fase 8 — S3 y AWS Batch

## Objetivo y alcance

Separar el procesamiento de movimientos diarios de las operaciones transaccionales de las APIs de bodega. La implementación permite exportar movimientos de tres PostgreSQL, generar CSV por fecha y un manifiesto SHA-256, ejecutar un trabajo AWS Batch Fargate que produce el resumen JSON en S3 y registrar el resultado para evitar reprocesamientos de fechas completadas.

**Estado al 23 de noviembre de 2026:** el flujo local de exportación PostgreSQL → S3 ha sido comprobado, y la definición AWS Batch Fargate revisión 3 ejecutó con éxito una prueba de idempotencia. La revisión 2 procesó correctamente el reporte del 22 de noviembre (1 movimiento, entrada de 100 unidades). Las mejoras más recientes del manifiesto y la corrección UTC/Colombia se probaron localmente, pero aún no se publicó y verificó en Fargate una imagen que las contenga. EventBridge Scheduler está creado, **DISABLED**. La exportación periódica sin un equipo local encendido **no está implementada**.

## Arquitectura

1. Las APIs de las bodegas WH-001, WH-002 y WH-003 guardan `inventory_movements` en PostgreSQL independientes.
2. `services/batch/exportar_movimientos.py --date YYYY-MM-DD` consulta las tres bases. Selecciona el día comercial `America/Bogota` mediante límites UTC `[inicio, fin)` porque la columna `created_at` es `timestamp without time zone` y representa UTC.
3. El exportador escribe tres CSV en `inputs/movements/daily/YYYY-MM-DD/` y por último `manifest.json` con fecha, estado `COMPLETE`, bodega, clave y SHA-256 por archivo.
4. `services/batch/main.py --date YYYY-MM-DD` comprueba fecha, bodegas y hashes, calcula entradas/salidas/ajustes y publica `exports/daily-movements-YYYY-MM-DD.json`.
5. El backend de registro local usa PostgreSQL `batch_runs`; el backend cloud usa `batch-runs/YYYY-MM-DD.json` en S3 con escrituras condicionales. Una fecha en `SUCCEEDED` se omite al repetir el trabajo.

## Rutas de S3

- `inputs/movements/daily/YYYY-MM-DD/WH-001.csv`
- `inputs/movements/daily/YYYY-MM-DD/WH-002.csv`
- `inputs/movements/daily/YYYY-MM-DD/WH-003.csv`
- `inputs/movements/daily/YYYY-MM-DD/manifest.json`
- `exports/daily-movements-YYYY-MM-DD.json`
- `batch-runs/YYYY-MM-DD.json`

## Ejecución manual reproducible

Se requieren AWS CLI perfil `PerfilUniversidad` vigente, Docker con las tres bases saludables, acceso a la región `us-east-1` y bucket `warehouse-platform-santi-2026`. 

Desde la raíz del repositorio (PowerShell):

```powershell
docker build -t warehouse-batch:local ./services/batch

docker create --name warehouse-export-demo --network compose_wh001 `
  --mount "type=bind,source=$env:USERPROFILE\.aws,target=/root/.aws,readonly" `
  -e AWS_PROFILE=PerfilUniversidad -e AWS_DEFAULT_REGION=us-east-1 `
  -e REPORT_BUCKET=warehouse-platform-santi-2026 `
  -e WH001_DATABASE_URL="postgresql+psycopg2://admin:localdev@wh001_db:5432/platform" `
  -e WH002_DATABASE_URL="postgresql+psycopg2://admin:localdev@wh002_db:5432/platform" `
  -e WH003_DATABASE_URL="postgresql+psycopg2://admin:localdev@wh003_db:5432/platform" `
  --entrypoint python warehouse-batch:local exportar_movimientos.py --date 2026-11-22

docker network connect compose_wh002 warehouse-export-demo
docker network connect compose_wh003 warehouse-export-demo
docker start -a warehouse-export-demo
docker rm warehouse-export-demo
```

Las cadenas anteriores usan las contraseñas locales de desarrollo predeterminadas; configurarlas en variables de entorno o un secreto para otros entornos. No ejecutar automáticamente si las bases no están disponibles. La exportación por fecha reemplaza objetos CSV y el manifiesto: no editar retroactivamente entradas de fechas que ya tengan un reporte `SUCCEEDED` sin un procedimiento de corrección auditado.

Validación y ejecución local usando S3 real:

```powershell
$env:AWS_PROFILE="PerfilUniversidad"
$env:AWS_DEFAULT_REGION="us-east-1"
$env:REPORT_BUCKET="warehouse-platform-santi-2026"
$env:BATCH_REGISTRY_BACKEND="s3"
python -m unittest discover -s services/batch/tests -p "test_*.py" -v
python -m compileall -q services/batch
# Seleccionar una fecha que NO figure ya como SUCCEEDED:
python services/batch/main.py --date YYYY-MM-DD
```

Para AWS Fargate, se requiere construir y publicar la imagen actualizada en ECR, registrar una nueva revisión de `warehouse-platform-inventory` y enviar un único trabajo a `warehouse-platform-queue`. No repetir `submit-job` si el comando ya devolvió `jobId`.

## Evidencias realizadas

- Tres PostgreSQL saludables, todos con `TimeZone=UTC`.
- Exportación del 22/11/2026: WH-001 0, WH-002 1 (RECEIPT, 100), WH-003 0.
- `manifest.json` en S3 con estado COMPLETE y SHA-256 de los 3 CSV; validación directa exitosa.
- 8 pruebas unitarias: 5 de manifiesto y 3 de fechas; todas `OK`.
- AWS Batch revisión 2: SUCCEEDED, salida 0, reporte `exports/daily-movements-2026-11-22.json` con +100 neto.
- AWS Batch revisión 3: SUCCEEDED, salida 0, detectó `2026-11-21` ya completado y omitió reprocesamiento.
- Registro S3 del 22/11/2026: SUCCEEDED, attempt_count=1, s3_key correcto.
- EventBridge Scheduler `warehouse-platform-daily-movements` configurado en `cron(0 23 * * ? *)`, `America/Bogota`, **DISABLED**.

## Respuestas conceptuales de la guía

**¿Por qué no generar el reporte dentro del request HTTP?** Porque la consulta de múltiples bodegas, exportación y agregación puede ser lenta o fallar parcialmente, aumentando la latencia de la API y acoplando las transacciones al reporte. Un trabajo separado permite reintentos, historial y escalabilidad.

**¿Cuándo usar Batch?** Para un procesamiento periódico o masivo, tolerante a ejecución diferida, que consolida datos de varias fuentes y genera reportes almacenados.

**¿Cuándo usar un worker?** Para tareas asíncronas continuas de menor granularidad desencadenadas por mensajes (p. ej., cambios de inventario y outbox/RabbitMQ), sin esperar una ejecución diaria.

**¿Cuándo usar Lambda?** Para transformaciones y validaciones acotadas activadas por eventos S3, sin gestionar contenedores permanentes; no reemplaza automáticamente al Batch para reportes masivos de larga duración.

## Limitaciones y siguientes mejoras

1. La fuente real de datos sigue en Docker local; para operación 100 % cloud se requiere desplegar PostgreSQL o un proceso exportador conectado de forma segura en infraestructura accesible desde AWS. **No activar Scheduler mientras el origen no esté actualizado y disponible.**
2. El cron a las 23:00 Colombia ocurre antes del cierre del día colombiano, por lo que no puede producir un reporte completo de ese día. Para el reporte del día completo se recomienda programar después de medianoche y procesar explícitamente la fecha anterior; esto requiere actualizar y volver a probar código/definición de trabajo y Scheduler.
3. `RUNNING` queda bloqueado si el contenedor termina sin registrar `FAILED`. Se requiere recuperación auditada basada en estado real del job, o un protocolo de lease con control de concurrencia antes de considerarlo completamente tolerante a fallos.
4. En la implementación actual el manifiesto verifica hashes y después se vuelve a leer cada objeto CSV; para eliminar la ventana de carrera se debe construir el reporte a partir de los mismos bytes validados, o usar objetos versionados/inmutables.
5. No hay evidencia aún de una ejecución Fargate **posterior** a la última edición (manifiesto + fechas UTC/Colombia); publicar una nueva revisión y realizar prueba con fecha inédita antes de afirmar que esa versión está desplegada.
6. La programación en AWS Academy no garantiza conservación de recursos tras el cierre definitivo del laboratorio. El repositorio es la fuente de entrega reproducible.

## Relación con la rúbrica oficial

- **Varias bodegas:** WH-001, WH-002 y WH-003.
- **Generar reporte:** agregados por bodega, entradas, salidas, ajustes, balance neto.
- **S3:** CSV, manifiesto, reporte, registro.
- **Registrar ejecución:** PostgreSQL local / S3 cloud.
- **Reejecución:** idempotencia de fecha SUCCEEDED; reintentos FAILED en S3 con condiciones de escritura.
