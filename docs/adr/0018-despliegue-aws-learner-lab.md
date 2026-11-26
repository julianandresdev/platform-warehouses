# ADR-0018 — Despliegue en AWS Learner Lab

## Estado

Aceptado. Implementado y probado en el laboratorio el 26 de noviembre de 2026 (S-09, issue #30). Responsable asignado: Santiago.

## Contexto y alternativas

El despliegue debe poder reconstruirse durante sesiones de laboratorio y quedar dentro del presupuesto. Crear recursos manualmente sirve para un ensayo, pero dificulta reproducirlos y comprobar el desmontaje. Terraform registra la configuración y permite revisar los cambios antes de aplicarlos.

## Decisión

Usar Terraform para aprovisionar la infraestructura de AWS. El plan contempla imágenes en ECR, servicios en EC2, PostgreSQL en RDS, un bucket S3 privado y Lambda activada por eventos. Usar perfiles y roles autorizados por el laboratorio, ejecutar una prueba de humo, registrar costos y conservar evidencia del desmontaje al terminar la sesión.

## Consecuencias y validación

- **Topología probada:** una EC2 `t3.large` con toda la plataforma en Compose (imágenes de ECR), WH-001 en RDS, S3 con la Lambda y la central con IP elástica para que la Lambda conozca su URL. Humo, batch → S3 → Lambda → central y la demo corrieron; después `terraform destroy` dejó la cuenta limpia. Ver [aws.md](../aws.md) y la [evidencia](../evidencias/fase-9/).
- **Una sola EC2** concentra todo: no hay alta disponibilidad, y es lo que cabe en el laboratorio y en el presupuesto.
- **Arranque por S3:** la instancia descarga el `docker-compose.yaml` y los SQL de `s3://<bucket>/deploy/`, que sube `scripts/aws-bundle.sh`. Así no hace falta SSH ni construir en la instancia.
- **Sin SSH ni SSM:** no hay forma de entrar a la instancia. Los logs del arranque y de los contenedores se suben a `logs/` en S3 para diagnosticar.
- **El bucket se crea con la CLI de AWS**, no con `aws_s3_bucket`, porque una política del laboratorio impide leer el recurso (detalle en aws.md).
- **Secretos:** la clave de RDS y las API keys quedan en el estado de Terraform y en el `user_data`; la de la central, además, en una variable de entorno de la Lambda. Es aceptable en el laboratorio, no en producción.
- **Costo:** estimado en menos de USD 0,10 para la sesión (no medido).
