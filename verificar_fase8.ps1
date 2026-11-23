
$ErrorActionPreference = "Stop"

Write-Host "=== FASE 8: Verificacion final ==="

# 1. Comprobar sintaxis
Write-Host "`n[1] Sintaxis Python"
python -m compileall -q services/batch
if ($LASTEXITCODE -ne 0) {
    throw "Error de sintaxis"
}

# 2. Ejecutar pruebas
Write-Host "`n[2] Pruebas automatizadas"
python -m unittest discover `
    -s services/batch/tests `
    -p "test_*.py" -v

if ($LASTEXITCODE -ne 0) {
    throw "Pruebas fallidas"
}

# 3. Verificar AWS
Write-Host "`n[3] Conexion AWS"
aws sts get-caller-identity `
    --profile PerfilUniversidad `
    --query Account --output text

if ($LASTEXITCODE -ne 0) {
    throw "Error de credenciales AWS"
}

# 4. Verificar AWS Batch
Write-Host "`n[4] AWS Batch"
aws batch describe-job-definitions `
    --job-definition-name warehouse-platform-inventory `
    --status ACTIVE `
    --region us-east-1 `
    --profile PerfilUniversidad `
    --query "jobDefinitions[].{Revision:revision,Estado:status}" `
    --output table

# 5. Verificar Scheduler
Write-Host "`n[5] EventBridge Scheduler"
aws scheduler get-schedule `
    --name warehouse-platform-daily-movements `
    --region us-east-1 `
    --profile PerfilUniversidad `
    --query "{Nombre:Name,Estado:State,Zona:ScheduleExpressionTimezone}" `
    --output json

# 6. Verificar archivos S3
Write-Host "`n[6] Archivos S3"
aws s3 ls `
    s3://warehouse-platform-santi-2026/inputs/movements/daily/2026-11-22/ `
    --profile PerfilUniversidad

Write-Host "`nVerificaciones ejecutadas."
