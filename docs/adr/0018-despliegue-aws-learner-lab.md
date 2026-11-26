# ADR-0018 — Despliegue en AWS Learner Lab

## Estado

Propuesto. Santiago debe confirmar la topología final y la evidencia del laboratorio.

## Contexto y alternativas

El despliegue debe poder reconstruirse durante sesiones de laboratorio y quedar dentro del presupuesto. Crear recursos manualmente sirve para un ensayo, pero dificulta reproducirlos y comprobar el desmontaje. Terraform registra la configuración y permite revisar los cambios antes de aplicarlos.

## Decisión

Usar Terraform para aprovisionar la infraestructura de AWS. El plan contempla imágenes en ECR, servicios en EC2, PostgreSQL en RDS, un bucket S3 privado y Lambda activada por eventos. Usar perfiles y roles autorizados por el laboratorio, ejecutar una prueba de humo, registrar costos y conservar evidencia del desmontaje al terminar la sesión.

## Consecuencias y validación

La topología depende de permisos, cuotas, región y estado de Terraform. La [configuración disponible](../../infrastructure/terraform/main.tf) documenta S3, Lambda, CloudWatch y permisos asociados. La validación de la topología completa, el runbook y la comprobación de recursos apagados quedan en [S-09](https://github.com/julianandresdev/platform-warehouses/issues/30). Ver también [despliegue AWS](../aws.md).
