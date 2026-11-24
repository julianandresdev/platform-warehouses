# Fase 9 — AWS Lambda, S3 y EventBridge

## 1. Objetivo

Implementar procesamiento serverless basado en eventos, mediante una función AWS Lambda que detecta reportes JSON en Amazon S3, valida su contenido, transforma los datos y publica eventos en Amazon EventBridge.

## 2. Arquitectura

**AWS Batch Fargate → Amazon S3 → AWS Lambda → Amazon EventBridge**

1. AWS Batch genera un reporte consolidado de inventarios.
2. El reporte se almacena como JSON en el prefijo `exports/` de S3.
3. S3 activa automáticamente Lambda mediante un evento `ObjectCreated`.
4. Lambda descarga y valida el reporte.
5. Lambda genera un resumen con los resultados de las tres bodegas.
6. Publica el evento `InventoryReportCreated` en EventBridge.
7. CloudWatch registra el procesamiento, los rechazos y los errores.

## 3. Implementación

**Código:** `services/lambda/handler.py`

**Función:** `warehouse-platform-export-handler`

**Runtime:** Python 3.12

**Región:** `us-east-1`

**Bucket:** `warehouse-platform-santi-2026`

La función procesa archivos JSON ubicados bajo `exports/`.

Las validaciones incluyen:

- Tipo de reporte `daily_inventory_movements`.
- Fecha válida.
- Presencia de las bodegas WH-001, WH-002 y WH-003.
- Estructura y cantidad de movimientos.
- Tipos y cantidades válidos.
- Consistencia de los totales por bodega y generales.

Los reportes inválidos son rechazados y registrados en CloudWatch sin publicar un evento.

Los errores operativos de S3 o EventBridge se propagan como excepciones.

## 4. Publicación en EventBridge

| Propiedad | Valor |
|---|---|
| Source | `warehouse.platform` |
| DetailType | `InventoryReportCreated` |
| EventBusName | `default` |
| Formato del detalle | JSON |

El evento publicado incluye la ubicación del archivo en S3, la fecha, las tres bodegas, la cantidad de movimientos, las entradas, salidas, ajustes y el cambio neto.

Lambda comprueba `FailedEntryCount` para detectar errores de publicación.

## 5. Infraestructura

La configuración Terraform se encuentra en `infrastructure/terraform/`.

Incluye:

- Bucket S3.
- Bloqueo de acceso público y cifrado.
- Función AWS Lambda.
- CloudWatch Logs.
- Permisos de invocación desde S3.
- Notificación `ObjectCreated` para `exports/`.
- Permisos de lectura de S3 y publicación en EventBridge cuando Terraform crea el rol IAM.

La infraestructura AWS Batch se gestiona por separado mediante AWS CLI y scripts del proyecto.

## 6. Pruebas realizadas

**Pruebas unitarias:** `services/lambda/tests/test_handler.py`

Se ejecutaron cinco pruebas correctamente:

1. Procesamiento de reporte válido.
2. Rechazo de JSON malformado.
3. Rechazo de totales inconsistentes.
4. Rechazo de reporte sin una de las tres bodegas.
5. Detección de errores de publicación en EventBridge.

**Prueba real con JSON válido:**

- Archivo: `exports/phase9-test-20261123192057.json`.
- Resultado: `processed = 1`, `rejected = 0`.
- CloudWatch confirmó la publicación aceptada por EventBridge.

**Prueba real con JSON inválido:**

- Archivo: `exports/phase9-invalid-20261123192218.json`.
- Resultado: `processed = 0`, `rejected = 1`.
- El reporte fue rechazado sin publicar un evento.

## 7. Limitaciones

Se creó y habilitó la regla EventBridge `warehouse-platform-report-created` para eventos `InventoryReportCreated`.

Sin embargo, la política IAM de AWS Academy `voc-cancel-cred` deniega explícitamente las operaciones `events:PutTargets` y `events:ListTargetsByRule`.

Por tanto, se verificó que EventBridge aceptó la publicación, pero no se pudo verificar la entrega a un consumidor.

Esta limitación no impidió comprobar el funcionamiento principal de Lambda.

## 8. Comparación de tecnologías

| Característica | Worker | AWS Batch | AWS Lambda |
|---|---|---|---|
| Ejecución | Continua | Por trabajo | Por invocación |
| Activación | Mensajes | Manual o programada | Eventos |
| Escalamiento | Configurado | Administrado/configurado | Administrado |
| Estado persistente | Externo | Externo | Externo |
| Uso principal | Procesos asíncronos | Procesamiento masivo | Procesamiento corto por eventos |

AWS Lambda se seleccionó porque el procesamiento del reporte es acotado y se activa automáticamente cuando aparece un archivo en S3.

## 9. Conclusión

Se implementó y probó el flujo S3 → AWS Lambda → EventBridge.

La función valida los reportes de inventario, rechaza información inconsistente, genera un resumen y publica eventos para permitir futuras integraciones.

La funcionalidad principal de la fase 9 está comprobada. La entrega del evento a un consumidor permanece sin verificar debido a restricciones de IAM del laboratorio.