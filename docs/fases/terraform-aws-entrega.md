# Infraestructura AWS — Terraform

## Recursos implementados

La infraestructura de las fases 8 y 9 utiliza Amazon S3, AWS Batch Fargate, AWS Lambda, Amazon EventBridge y Amazon CloudWatch.

Terraform administra la configuración declarativa de S3, Lambda y AWS Batch mediante los archivos de `infrastructure/terraform/`.

Los recursos existentes de AWS Batch fueron incorporados al estado de Terraform mediante `terraform import`.

## Validaciones realizadas

- `terraform init`: ejecutado correctamente.
- `terraform validate`: configuración válida.
- AWS Batch: ejecución de la revisión 4 con resultado `SUCCEEDED` y código de salida `0`.
- AWS Lambda: estado `Active` y última actualización `Successful`.
- Código de Lambda: coincidencia SHA-256 entre el archivo local `handler.py` y el desplegado en AWS.
- AWS Batch Job Queue: estado `ENABLED`, prioridad `1` y entorno Fargate asociado con orden `1`.

## Diferencias pendientes del plan

El último `terraform plan -refresh=false` mostró:

`Plan: 0 to add, 2 to change, 0 to destroy.`

Las diferencias corresponden a:

1. **AWS Batch Job Queue:** transición entre el atributo antiguo `compute_environments` y `compute_environment_order`. La configuración real de AWS fue comprobada y coincide funcionalmente con la declarada.
2. **AWS Lambda:** diferencia entre el hash del paquete ZIP generado localmente y el desplegado en AWS. Se verificó que ambos paquetes contienen el mismo archivo `handler.py`, con idéntico hash SHA-256.

No se ejecutó `terraform apply` para evitar modificaciones innecesarias a los recursos operativos.

## Restricción de AWS Academy

El entorno académico bloquea la operación `s3:GetBucketObjectLockConfiguration` mediante una política de control de servicios (SCP).

Por esta razón no fue posible completar un plan integral con actualización de todos los recursos desde AWS. El plan utilizado con `-refresh=false` constituye una verificación de configuración frente al estado guardado, no una comprobación completa de ausencia de diferencias remotas.

## Limitaciones de reproducibilidad

La configuración actual incluye identificadores específicos del laboratorio, como la cuenta AWS, subredes, grupos de seguridad, roles IAM y una imagen de Amazon ECR.

Estos valores deben parametrizarse o reemplazarse cuando se despliegue la infraestructura en otra cuenta o entorno.

La automatización diaria de AWS Batch permanece deshabilitada porque el exportador depende actualmente de bases PostgreSQL locales.

## Estado de entrega

Las funcionalidades principales de las fases 8 y 9 fueron verificadas mediante ejecuciones reales y pruebas unitarias. La infraestructura cuenta con configuración Terraform, pero su reconciliación completa y la reproducción en un entorno AWS nuevo permanecen pendientes de validación.