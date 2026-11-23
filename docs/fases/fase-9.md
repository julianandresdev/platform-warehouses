\# Fase 9 — Integración Serverless con AWS Lambda, S3 y EventBridge



\## 1. Objetivo



Implementar una arquitectura serverless que permita detectar automáticamente los reportes generados en Amazon S3 y publicar eventos en Amazon EventBridge mediante AWS Lambda.



\## 2. Arquitectura



El procesamiento sigue este flujo:



\*\*AWS Batch Fargate → Amazon S3 → AWS Lambda → Amazon EventBridge\*\*



1\. AWS Batch genera el reporte consolidado de inventarios.

2\. El reporte JSON se guarda en el prefijo `exports/` de Amazon S3.

3\. S3 activa automáticamente una función AWS Lambda.

4\. Lambda identifica el reporte generado.

5\. Lambda publica un evento en Amazon EventBridge.



\## 3. Tecnologías utilizadas



\- AWS Lambda con Python 3.12.

\- Amazon S3.

\- Amazon EventBridge.

\- Amazon CloudWatch Logs.

\- Terraform.

\- AWS CLI.

\- Boto3.



\## 4. Implementación de Lambda



El código fuente se encuentra en:



`services/lambda/handler.py`



La función implementada se llama:



`warehouse-platform-export-handler`



La función recibe eventos de Amazon S3 y verifica que los archivos pertenezcan al prefijo `exports/`.



Para cada archivo válido, utiliza `put\_events()` para publicar un evento en EventBridge.



Configuración del evento:



| Propiedad | Valor |

|---|---|

| Source | `warehouse.platform` |

| DetailType | `InventoryReportCreated` |

| EventBusName | `default` |



El detalle del evento incluye el nombre del bucket, la clave del archivo y el tipo de evento recibido desde S3.



La función comprueba el campo `FailedEntryCount` de la respuesta de EventBridge y genera un error si existen publicaciones fallidas.



\## 5. Infraestructura con Terraform



Se utilizó Terraform para configurar la infraestructura serverless de la fase 9.



Entre los componentes configurados se encuentran:



\- Bucket S3.

\- Protección contra acceso público.

\- Cifrado del bucket.

\- Función AWS Lambda.

\- Grupo de registros de CloudWatch.

\- Permiso de invocación de Lambda desde S3.

\- Notificación de S3 para objetos creados bajo el prefijo `exports/`.



La infraestructura se encuentra en:



`infrastructure/terraform/`



La función utiliza la variable de entorno:



`EVENT\_BUS\_NAME=default`



\## 6. Configuración AWS



| Recurso | Configuración |

|---|---|

| Región | `us-east-1` |

| Bucket | `warehouse-platform-santi-2026` |

| Lambda | `warehouse-platform-export-handler` |

| Runtime | Python 3.12 |

| Prefijo de S3 | `exports/` |

| Bus EventBridge | `default` |

| Grupo CloudWatch | `/aws/lambda/warehouse-platform-export-handler` |



\## 7. Pruebas realizadas



Se verificó la ejecución de Lambda al crear un archivo de prueba en S3.



Posteriormente, AWS Batch generó el reporte:



`exports/inventory-report-20261123T051125636513Z.json`



CloudWatch confirmó el procesamiento:



`2026-11-23T05:11:29.713Z`



`Reporte procesado: s3://warehouse-platform-santi-2026/exports/inventory-report-20261123T051125636513Z.json`



Los registros mostraron la finalización de la ejecución sin errores.



También se verificó mediante IAM que el rol utilizado tenía permiso para ejecutar `events:PutEvents` sobre el bus `default`.



Dado que el mensaje de procesamiento se registra después de la llamada a `put\_events()` y de comprobar `FailedEntryCount`, los resultados proporcionan evidencia de que EventBridge aceptó la publicación del evento.



\## 8. Limitaciones y consideraciones



\- No se configuró una regla de EventBridge específica para consumir los eventos `InventoryReportCreated`.

\- La solución valida la publicación del evento, pero no una acción posterior ejecutada por un consumidor.

\- La configuración de Terraform puede requerir adaptaciones según las restricciones IAM de la cuenta AWS.

\- La implementación de AWS Batch se realizó mediante AWS CLI; sus recursos no forman parte de la infraestructura Terraform de la fase 9.



\## 9. Conclusión



Se implementó y verificó una integración serverless para procesar automáticamente las notificaciones de reportes de inventario generados en Amazon S3.



AWS Lambda recibió el evento de S3, identificó el reporte y realizó la publicación correspondiente en Amazon EventBridge.



Esta arquitectura permite desacoplar la generación de reportes de otros servicios que podrían procesar los eventos en futuras ampliaciones.

