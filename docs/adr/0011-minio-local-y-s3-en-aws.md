# ADR-0011 — MinIO local y Amazon S3 en AWS

## Estado

MinIO configurado en Docker Compose. Pendiente de revisión de Santiago
y de validar el despliegue de AWS desde esta rama.

## Contexto

El procesamiento por lotes necesita almacenar reportes como objetos.
El entorno local debe permitir probar esa integración sin depender de
una sesión del laboratorio de AWS.

## Alternativas consideradas

Usar Amazon S3 en todos los entornos daría paridad con AWS, con
dependencia de conexión, permisos y disponibilidad del laboratorio.
Un almacenamiento local compatible con la API de S3 permite ejecutar
el flujo con Compose y verificar la integración con AWS por separado.

## Decisión

Usar MinIO para las pruebas locales y Amazon S3 como destino en AWS.
Compose inicializa el bucket local con `minio_init` y configura el
endpoint de S3 del job Batch mediante `S3_ENDPOINT_URL`.

## Consecuencias

El flujo local puede ejecutarse sin el laboratorio de AWS. Los permisos
IAM, las notificaciones de objetos y el disparo de Lambda se validan en
AWS. Los objetos del entorno local persisten en un volumen de MinIO.

## Validación

Ver el [Compose de Batch](../../infrastructure/compose/compose.batch.yml)
y las [decisiones de despliegue](../architecture.md#6-despliegue).
