# AWS

## Terraform

Toda la infraestructura de AWS se crea con Terraform desde `infrastructure/terraform/`, organizada en módulos:

| Módulo | Recursos |
| --- | --- |
| `network` | VPC por defecto (`data`), security groups de la EC2 y de RDS. |
| `ecr` | Repositorios `warehouse`, `central`, `batch` e `iot` (escaneo al subir la imagen). |
| `compute` | EC2 con `LabInstanceProfile` y `user_data` que instala Docker y Compose, hace login a ECR, escribe el `.env` con `templatefile`, descarga el paquete de despliegue de S3 (`deploy/`) y ejecuta `docker compose pull && docker compose up -d`. Sube su log y los de los contenedores a `logs/` en S3. La IP elástica (`aws_eip`, en la raíz) se asocia a la instancia. |
| `database` | `aws_db_instance` PostgreSQL 16, `db.t3.micro`, usuario `warehouse` (RDS no admite `admin`), clave `sensitive`, `skip_final_snapshot = true` (la base de WH-001). |
| `storage` | Bucket privado (se crea con la CLI de AWS, ver «Hallazgos del laboratorio»), bloqueo de acceso público, cifrado AES256 y notificación a la Lambda para `reports/*.json`. |
| `lambda` | `archive_file` del código, rol `LabRole` leído con `data`, `aws_lambda_permission` para S3 y las variables `CENTRAL_API_URL` y `CENTRAL_API_KEY`. |

### Reglas de red

- **APIs:** los puertos de `public_api_ports` quedan abiertos a Internet (solo para la demo): 8004 (central, también la usa la Lambda), 8101, 8102 y 8103.
- **SSH (22), RabbitMQ (15672) y Grafana (3000):** solo desde `team_cidr_blocks`.
- **RDS (5432):** solo desde el security group de la EC2.

### Uso

```bash
cd infrastructure/terraform
cp terraform.tfvars.example terraform.tfvars     # editar bucket, IP del equipo, puertos y tipo de instancia
export TF_VAR_db_password='<clave de RDS>'       # sin : / ? # @ ; no va en el archivo
export TF_VAR_api_key='<X-API-Key de las bodegas>'
export TF_VAR_central_api_key='<X-API-Key de la central>'
terraform init
terraform validate
terraform plan
```

`terraform.tfvars` y el estado están en el `.gitignore`.

### Outputs

`ec2_public_ip`, `rds_endpoint` y `s3_bucket` (nombre del bucket); además `lambda_name`, `region`, `eventbridge_bus` y `ecr_repository_urls`.

### Variables obligatorias (sin valor por defecto)

`bucket_name`, `team_cidr_blocks`, `public_api_ports`, `instance_type`, `db_password`, `api_key` y `central_api_key`. El tipo de instancia depende de lo que permita el Learner Lab (tarea S-01); el ejemplo usa `t3.large` solo como marcador.

### Migración del estado anterior

La versión previa de este directorio tenía todo en `main.tf`. Los bloques `moved` conservan el bucket, su notificación, la Lambda, su log group y el permiso al pasar a módulos. El rol IAM propio que creaba esa versión (y sus políticas) desaparece: la Lambda usa `LabRole`, y un `terraform plan` sobre un estado anterior lo mostrará como recurso a destruir.

## Despliegue completo (S-09)

La EC2 corre toda la plataforma con [`infrastructure/aws/docker-compose.yaml`](../infrastructure/aws/docker-compose.yaml): RabbitMQ, las tres bodegas (API, worker de outbox y worker de comandos; Redis por bodega) y la central (API, worker y base). **WH-001 usa RDS**; WH-002, WH-003 y la central usan PostgreSQL en contenedor. El servicio `wh001_db_init` aplica schema, migraciones y seed en RDS la primera vez. El servicio `batch` (profile `batch`) corre el reporte diario. Las imágenes salen de ECR y S3 se accede con el perfil de la instancia (sin credenciales en el disco).

No se despliega Prometheus ni Grafana en AWS; la observabilidad se demuestra en local (ver [observability.md](observability.md)).

### Runbook

Requisitos: AWS CLI con el perfil del laboratorio (`export AWS_PROFILE=lab`), Terraform, Docker con `buildx` y un `terraform.tfvars` (a partir del ejemplo).

```bash
cd infrastructure/terraform
terraform init

# 1. ECR, S3 y Lambda primero: las imágenes y el paquete de despliegue necesitan dónde subirse.
terraform apply -target=module.ecr -target=module.storage

# 2. Imágenes (linux/amd64) y paquete de despliegue (docker-compose.yaml y sql/) en S3.
cd ../..
scripts/push-ecr.sh
scripts/aws-bundle.sh <bucket>

# 3. El resto: red, RDS y EC2. El arranque tarda ~3 min tras crearse la instancia.
cd infrastructure/terraform && terraform apply

# 4. Prueba de humo contra la IP de salida `ec2_public_ip`.
cd ../.. && API_KEY=... CENTRAL_API_KEY=... scripts/smoke.sh <ec2_public_ip>

# 5. Reporte diario (S3 → Lambda → central): ver «Reporte diario» más abajo.

# 6. Al terminar la sesión: todo se borra.
cd infrastructure/terraform && terraform destroy
```

`scripts/smoke.sh` comprueba `/health` y `/health/ready` de las tres bodegas, `GET /inventory/P-001` en cada una, la central y la vista global, y completa una transferencia de punta a punta por la Saga. Sale con código 1 si algo falla.

**Reporte diario.** La EC2 no tiene acceso por SSH (no hay llave en la plantilla), así que el batch se corrió desde la laptop contra las APIs públicas de la EC2 y el bucket real:

```bash
PYTHONPATH=services/batch:services/common \
WH001_API_URL=http://<ip>:8101 WH002_API_URL=http://<ip>:8102 WH003_API_URL=http://<ip>:8103 API_KEY=... \
CENTRAL_API_URL=http://<ip>:8004 CENTRAL_API_KEY=... S3_BUCKET=<bucket> \
python -m batch.daily_report --date 2026-11-26
```

Con acceso a la instancia sería `docker compose --profile batch run --rm batch python -m batch.daily_report --date YYYY-MM-DD`.

### Evidencia de la sesión del 26 de noviembre de 2026

Está en [`docs/evidencias/fase-9/`](evidencias/fase-9/) (salida de la CLI de AWS, no capturas de la consola). El número de cuenta se reemplazó por `<cuenta>`.

| Recurso | Archivo | Qué muestra |
| --- | --- | --- |
| EC2 | [`ec2.txt`](evidencias/fase-9/ec2.txt) | `t3.large` en ejecución con `LabInstanceProfile` y la IP elástica |
| ECR | [`ecr.txt`](evidencias/fase-9/ecr.txt) | imágenes `warehouse`, `central` y `batch` |
| RDS | [`rds.txt`](evidencias/fase-9/rds.txt) | `db.t3.micro`, PostgreSQL 16, no pública |
| S3 | [`s3.txt`](evidencias/fase-9/s3.txt) | objetos de `warehouses/`, `reports/` y `metadata/`, y el metadato `correlation-id` |
| Lambda | [`lambda.txt`](evidencias/fase-9/lambda.txt), [`cloudwatch-lambda.txt`](evidencias/fase-9/cloudwatch-lambda.txt) | configuración y registros de CloudWatch (`report_validated`, `REPORT`) |
| Humo | [`smoke.txt`](evidencias/fase-9/smoke.txt) | 12 comprobaciones, todas `PASS`, incluida una transferencia `COMPLETED` |
| Demo | [`demo-en-aws.txt`](evidencias/fase-9/demo-en-aws.txt) | movimiento, `X-Cache` MISS/HIT, vista global, transferencia 100 → 74/51 y la compensación por `SKU_NOT_FOUND` |
| Destroy | [`despues-del-destroy.txt`](evidencias/fase-9/despues-del-destroy.txt) | cuenta sin instancias, IP elásticas, RDS, repositorios, buckets, funciones ni log groups del proyecto |

**Criterio de #29 (S3 → metadato + central + CloudWatch):** el batch subió `reports/daily/2026-11-26/summary.json` con el metadato `correlation-id: COR-20261126-e8ddb6c4`; la Lambda escribió `metadata/reports/daily/2026-11-26/summary.json` (`VALID`, 33 registros, SHA-256) y registró en la central; en CloudWatch el log `report_validated` lleva el mismo `correlation_id`. Se comprobó que la central guardó la fila repitiendo `POST /internal/reports` con el mismo cuerpo: respondió 200 (actualización) y no 201.

### Costo

Estimado con precios de lista de `us-east-1` (el laboratorio no deja consultar Cost Explorer, así que **no es una medición**):

| Recurso | Tiempo encendido | Estimado |
| --- | --- | --- |
| EC2 `t3.large` (dos instancias; la primera falló al arrancar) | ≈ 18 min | USD 0,03 |
| RDS `db.t3.micro` | ≈ 25 min | USD 0,01 |
| IP elástica | menos de 1 h (se creó en el primer `apply`, sin hora registrada) | menos de USD 0,01 |
| ECR, S3, Lambda y CloudWatch | uso mínimo | menos de USD 0,01 |
| **Total estimado** | | **menos de USD 0,10** |

El tiempo sale de las marcas de Terraform (RDS creada 05:08, EC2 destruida 05:27 y RDS destruida 05:28 UTC). La reserva de USD 15 del issue no se tocó.

### Hallazgos del laboratorio

- **`aws_s3_bucket` no funciona en este laboratorio.** Una política de la organización (SCP) niega `s3:GetBucketObjectLockConfiguration` y el proveedor la llama siempre al leer el recurso: falla con `AccessDenied` en las versiones 4.67, 5.0, 5.31 y 5.100. Por eso el módulo `storage` crea el bucket con `terraform_data` y la CLI de AWS (y lo borra en el `destroy`, vaciándolo si `force_destroy_bucket` es `true`); el acceso público, el cifrado y la notificación siguen siendo recursos de Terraform. Se quitó el bloque `moved` del bucket.
- **RDS PostgreSQL no admite el usuario `admin`** (palabra reservada del motor). El módulo `database` usa `warehouse` por defecto.
- **`t3.large` está permitido** (`run-instances --dry-run` respondió `DryRunOperation`) y `LabRole` y `LabInstanceProfile` existen.
- **La primera instancia no terminó de arrancar:** `central_db` quedó `unhealthy` y `docker compose up` se detuvo. Sin acceso por SSH no se pudo ver la causa. Se reemplazó la instancia con dos cambios a la vez: los archivos descargados de S3 quedaban con permisos 600 por el `umask 077` del `user_data` (ahora se dejan legibles, salvo el `.env`) y el `user_data` sube sus logs a `logs/` en S3. La segunda instancia arrancó bien; **no se confirmó cuál de los dos cambios, o si fue otra cosa, resolvió el problema.**
- **Sin llave SSH ni SSM no hay forma de entrar a la instancia.** Por eso los logs se suben a S3 y el batch se corrió desde fuera.
