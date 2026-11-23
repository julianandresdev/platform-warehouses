\# Fase 8 — Procesamiento Batch de Inventarios



\## 1. Objetivo



Implementar AWS Batch con AWS Fargate para consolidar automáticamente los inventarios de tres bodegas independientes (WH-001, WH-002 y WH-003).



\## 2. Arquitectura



El procesamiento sigue este flujo:



\*\*PostgreSQL → CSV → Amazon S3 → AWS Batch Fargate → Amazon S3 → AWS Lambda\*\*



Los inventarios se exportan desde las bases de datos PostgreSQL y se almacenan como archivos CSV en S3. AWS Batch ejecuta un contenedor Docker que procesa estos archivos y genera un reporte consolidado en formato JSON.



\## 3. Tecnologías utilizadas



\- Python 3.12 y Boto3.

\- Docker y Amazon ECR.

\- AWS Batch y AWS Fargate.

\- Amazon S3.

\- PostgreSQL.



\## 4. Implementación



El procesamiento se encuentra en `services/batch/main.py`.



Los archivos principales son:



\- `services/batch/main.py`: lectura de archivos CSV, validación, consolidación y generación del reporte.

\- `services/batch/Dockerfile`: construcción del contenedor.

\- `services/batch/requirements.txt`: dependencias de Python.



El programa lee los archivos `WH-001.csv`, `WH-002.csv` y `WH-003.csv` desde `inputs/inventory/` en S3.



Posteriormente, calcula los totales de inventario, unidades reservadas y unidades disponibles, y guarda un reporte JSON en `exports/`.



\## 5. Configuración en AWS



| Recurso | Configuración |

|---|---|

| Región | `us-east-1` |

| Repositorio ECR | `warehouse-platform-batch` |

| Entorno Fargate | `warehouse-platform-fargate` |

| Cola AWS Batch | `warehouse-platform-queue` |

| Definición | `warehouse-platform-inventory:1` |

| Bucket S3 | `warehouse-platform-santi-2026` |

| CPU | 0.25 vCPU |

| Memoria | 512 MiB |



La variable de entorno `REPORT\_BUCKET` identifica el bucket utilizado para leer y escribir los archivos.



\## 6. Ejecución del trabajo



Para iniciar el procesamiento, se utiliza:



```bash

aws batch submit-job \\

&#x20; --job-name warehouse-inventory-test-01 \\

&#x20; --job-queue warehouse-platform-queue \\

&#x20; --job-definition warehouse-platform-inventory:1 \\

&#x20; --region us-east-1

```



Para consultar el estado:



```bash

aws batch describe-jobs \\

&#x20; --jobs JOB\_ID \\

&#x20; --region us-east-1

```



\## 7. Resultados obtenidos



El trabajo `warehouse-inventory-test-01` finalizó correctamente con estado \*\*SUCCEEDED\*\*.



| Bodega | Unidades | Reservadas | Disponibles |

|---|---:|---:|---:|

| WH-001 | 50 | 5 | 45 |

| WH-002 | 100 | 0 | 100 |

| WH-003 | 75 | 10 | 65 |

| \*\*Total\*\* | \*\*225\*\* | \*\*15\*\* | \*\*210\*\* |



Se procesaron tres productos y se generó el siguiente reporte:



`exports/inventory-report-20261123T051125636513Z.json`



Se verificó directamente en Amazon S3 que los valores del archivo coincidían con los inventarios originales.



\## 8. Consideraciones técnicas



\- Para las pruebas, la exportación de PostgreSQL a CSV y la carga de los archivos en S3 se realizaron manualmente.

\- El contenedor en Fargate procesa archivos de S3; no establece conexiones directas con PostgreSQL.

\- La imagen Docker se almacena en Amazon ECR.

\- El trabajo utiliza un rol IAM con permisos para leer y escribir en S3.

\- La definición de AWS Batch se registró mediante AWS CLI.

\- La generación del reporte activa AWS Lambda mediante un evento de S3.



\## 9. Conclusión



Se implementó y verificó exitosamente el procesamiento distribuido de inventarios mediante AWS Batch Fargate.



La solución consolidó la información de tres bodegas, calculó correctamente las cantidades y generó un reporte JSON en Amazon S3, disponible para su posterior procesamiento por AWS Lambda.

