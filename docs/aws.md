# AWS — Estado de infraestructura y reproducibilidad

## Configuración existente

El directorio `infrastructure/terraform` contiene S3 (bucket privado con bloqueo de acceso público y cifrado), notificación S3 → Lambda, CloudWatch, EventBridge y AWS Batch Fargate. El archivo `terraform.tfvars.example` contiene **marcadores de posición** que deben sustituirse por identificadores del entorno. No subir `terraform.tfvars`, estado local, plan ni credenciales.

Comandos orientativos desde la raíz del repositorio:

```powershell
Copy-Item infrastructure/terraform/terraform.tfvars.example infrastructure/terraform/terraform.tfvars
# Editar terraform.tfvars con bucket, red, roles y ECR propios del laboratorio
terraform -chdir=infrastructure/terraform init
terraform -chdir=infrastructure/terraform validate
terraform -chdir=infrastructure/terraform plan -refresh=false
```

**Nota:** no ejecutar `apply` o `destroy` de manera automática. La infraestructura existente ya fue importada a un estado local. Para una cuenta limpia deben revisarse roles, recursos importados y estado remoto antes de cualquier ejecución.

## Hallazgos y limitaciones

- El entorno AWS Academy bloqueó `s3:GetBucketObjectLockConfiguration` por SCP, por lo cual un plan con refresco completo falla en ese laboratorio. `plan -refresh=false` **no sustituye** una verificación real de drift.
- El último plan conocido mostró dos cambios (`aws_batch_job_queue` por atributo heredado y `aws_lambda_function` por empaquetado ZIP). No hay confirmación de plan limpio.
- Se agregaron definiciones de red, repos ECR, EC2 con LabInstanceProfile y RDS PostgreSQL 16 en `platform.tf`, todas **desactivadas por defecto** (`provision_platform_resources=false`). No se ha validado creación/destrucción ni el arranque completo de Docker con secretos: por tanto, #27 no está aprobado ni demostrado en AWS.
- Learner Lab puede impedir crear roles IAM. `lambda_role_arn` debe apuntar a un rol existente o se debe utilizar un `data.aws_iam_role` según las políticas del laboratorio.
- El Scheduler de la fase 8 permanece deshabilitado: su origen PostgreSQL es local y la programación actual requiere rediseño para un cierre diario completo.

## Pruebas de funcionalidad realizadas

- AWS Batch revisión 4: `SUCCEEDED`, salida 0.
- Lambda: JSON válido procesado e inválido rechazado.
- EventBridge y CloudWatch: evento aceptado y registrado tras crear un objeto S3, evidenciado en `evidencias/fase-9/`.

**Estado para el reviewer:** funcionalidad AWS probada, pero no marcar el issue #27 como cerrado sin implementar y validar los componentes y criterios de aceptación restantes.
