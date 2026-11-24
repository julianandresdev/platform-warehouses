# Contratos revisados — PR #52

## Fase 8, issue #12

Se agregan endpoints GET `/inventory` y GET `/movements?from=&to=&page=` protegidos por `X-API-Key`, abstracción `services/common/common/storage.py`, CLI `python -m batch.daily_report --date YYYY-MM-DD`, salida a `warehouses/WH-00X/YYYY/MM/...` y `reports/daily/YYYY-MM-DD/summary.json`, estado `PARTIAL` y llamada HTTP `POST /internal/batch-runs`. El servicio de la API central **no está incluido** en el repositorio consultado. Es obligatorio configurarlo y validar el payload con sus responsables; por seguridad la CLI falla de manera visible cuando no se configura `CENTRAL_API_URL`.

## Fase 9, issue #29

El handler original conserva soporte para `exports/` y su publicación EventBridge. Para archivos bajo `reports/` agrega validación, metadata `metadata/reports/...` con hash, bytes, recuento, estado VALID/INVALID, log de `correlation-id` y POST autenticado `/internal/reports`. El HTTP central se declara obligatorio: no se inventa éxito cuando no hay endpoint. La variable `CENTRAL_API_KEY` no debe quedar en tfvars de Git; preferir Secrets Manager o SSM en despliegues reales.

## Terraform, issue #27

Se agregan definiciones opcionales de VPC default, security groups, repositorios ECR, EC2 y RDS PostgreSQL 16, deshabilitadas por defecto para **no crear recursos con coste ni modificar la infraestructura del laboratorio**. La instancia EC2 instala Docker, obtiene credenciales ECR y crea un `.env` sin secretos. El arranque automático de compose con secretos, el primer apply/destroy y conectividad RDS deben validarse en una cuenta de prueba. Activar el módulo con `provision_platform_resources=true` después de configurar password y red, y revisar `terraform plan`.

## Pruebas

Se agregaron pruebas unitarias nuevas para el contrato de Batch y Lambda. No equivalen a probar contra MinIO, la API central ni AWS Academy. Mantener los reportes de pruebas reales anteriores sin cambiarlos artificialmente.
