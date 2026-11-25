# AWS

## Terraform

Toda la infraestructura de AWS se crea con Terraform desde `infrastructure/terraform/`, organizada en módulos:

| Módulo | Recursos |
| --- | --- |
| `network` | VPC por defecto (`data`), security groups de la EC2 y de RDS. |
| `ecr` | Repositorios `warehouse`, `central`, `batch` e `iot` (escaneo al subir la imagen). |
| `compute` | EC2 con `LabInstanceProfile` y `user_data` que instala Docker y Compose, hace login a ECR, escribe el `.env` con `templatefile` y ejecuta `docker compose pull && docker compose up -d`. |
| `database` | `aws_db_instance` PostgreSQL 16, `db.t3.micro`, clave `sensitive`, `skip_final_snapshot = true` (la base de WH-001). |
| `storage` | Bucket privado (bloqueo de acceso público y cifrado AES256) con notificación a la Lambda para `reports/*.json`. |
| `lambda` | `archive_file` del código, rol `LabRole` leído con `data` y `aws_lambda_permission` para S3. |

### Reglas de red

- **APIs:** los puertos de `public_api_ports` quedan abiertos a Internet (solo para la demo).
- **SSH (22), RabbitMQ (15672) y Grafana (3000):** solo desde `team_cidr_blocks`.
- **RDS (5432):** solo desde el security group de la EC2.

### Uso

```bash
cd infrastructure/terraform
cp terraform.tfvars.example terraform.tfvars     # editar bucket, IP del equipo, puertos y tipo de instancia
export TF_VAR_db_password='<clave de RDS>'       # no va en el archivo
terraform init
terraform validate
terraform plan
```

`terraform.tfvars` y el estado están en el `.gitignore`. Para borrar todo al terminar la sesión del laboratorio: `terraform destroy`.

### Outputs

`ec2_public_ip`, `rds_endpoint` y `s3_bucket` (nombre del bucket); además `lambda_name`, `region`, `eventbridge_bus` y `ecr_repository_urls`.

### Variables obligatorias (sin valor por defecto)

`bucket_name`, `team_cidr_blocks`, `public_api_ports`, `instance_type` y `db_password`. El tipo de instancia depende de lo que permita el Learner Lab (tarea S-01); el ejemplo usa `t3.large` solo como marcador.

### Migración del estado anterior

La versión previa de este directorio tenía todo en `main.tf`. Los bloques `moved` conservan el bucket, su notificación, la Lambda, su log group y el permiso al pasar a módulos. El rol IAM propio que creaba esa versión (y sus políticas) desaparece: la Lambda usa `LabRole`, y un `terraform plan` sobre un estado anterior lo mostrará como recurso a destruir.

### Qué no está verificado

- **`terraform plan`, `apply` y `destroy` no se ejecutaron:** requieren credenciales del Learner Lab. Sí se ejecutaron `terraform fmt`, `init -backend=false` y `validate` (válido), y se comprobó cómo se renderiza el `user_data`.
- **La Lambda empaqueta `services/lambda/report_validator/`**, carpeta que llega con S-08 (#29). Hasta entonces `plan` falla en `archive_file`; `validate` no.
- **El `user_data` no se probó en una EC2.** El plugin de Compose se descarga de GitHub (`compose_version`) porque Amazon Linux 2023 no lo trae. El último paso necesita un `docker-compose.yaml` dentro de `/opt/warehouse-platform`; cómo llega ese archivo a la EC2 lo define el despliegue (S-09, #30).
- **El `.env`** contiene `DATABASE_URL` (WH-001 en RDS), `S3_BUCKET`, `AWS_DEFAULT_REGION` y `ECR_REGISTRY`; el resto de variables que necesite el Compose de AWS se agregan con `extra_env_vars`.
- **Secretos:** la clave de RDS queda en el estado de Terraform y en el `user_data` de la instancia. Es aceptable en el laboratorio; no para producción.
