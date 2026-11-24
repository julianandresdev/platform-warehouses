param(
    [string]$Profile = "PerfilUniversidad",
    [string]$Region = "us-east-1",
    [string]$Repository = "warehouse-platform-batch",
    [string]$JobName = "warehouse-platform-inventory"
)

$ErrorActionPreference = "Stop"
$env:AWS_PROFILE = $Profile
$env:AWS_DEFAULT_REGION = $Region

function Assert-Last($descripcion) {
    if ($LASTEXITCODE -ne 0) { throw "$descripcion falló (exit code $LASTEXITCODE)" }
}

if (-not (Test-Path "services/batch/Dockerfile")) {
    throw "Ejecuta este script desde la raíz del repositorio platform-warehouses."
}

Write-Host "[1/6] Validación local..."
python -m compileall -q services/batch
Assert-Last "Sintaxis Python"
python -m unittest discover -s services/batch/tests -p "test_*.py" -v
Assert-Last "Pruebas automatizadas"

Write-Host "[2/6] Verificando cuenta AWS..."
$account = (aws sts get-caller-identity --profile $Profile --query Account --output text).Trim()
Assert-Last "AWS STS"
$ecr = "$account.dkr.ecr.$Region.amazonaws.com/$Repository"
$tag = "fase8-manifest-" + (Get-Date -Format "yyyyMMddHHmmss")

Write-Host "[3/6] Construyendo imagen Docker..."
docker build -t warehouse-batch:local ./services/batch
Assert-Last "Docker build"

Write-Host "[4/6] Publicando nueva imagen ECR..."
aws ecr get-login-password --region $Region --profile $Profile | docker login --username AWS --password-stdin "$account.dkr.ecr.$Region.amazonaws.com"
Assert-Last "ECR login"
docker tag warehouse-batch:local "${ecr}:$tag"
Assert-Last "Docker tag"
docker push "${ecr}:$tag"
Assert-Last "Docker push"
$digest = (aws ecr describe-images --repository-name $Repository --image-ids "imageTag=$tag" --region $Region --profile $Profile --query 'imageDetails[0].imageDigest' --output text).Trim()
Assert-Last "Verificar digest"
if ($digest -notmatch '^sha256:[a-f0-9]{64}$') { throw "Digest no válido: $digest" }

Write-Host "[5/6] Generando nueva revisión sin modificar las anteriores..."
$all = aws batch describe-job-definitions --job-definition-name $JobName --status ACTIVE --region $Region --profile $Profile --output json | ConvertFrom-Json
Assert-Last "Consultar job definitions"
$base = $all.jobDefinitions | Sort-Object revision -Descending | Select-Object -First 1
if ($null -eq $base) { throw "No existe ninguna definición ACTIVE de $JobName" }
$properties = $base.containerProperties
$properties.image = "${ecr}@${digest}"
# Conservar roles, memoria, CPU, red y configuración del contenedor vigente.
$containerPath = Join-Path $env:TEMP "warehouse-batch-container-new.json"
$properties | ConvertTo-Json -Depth 40 | Set-Content -Encoding ascii -Path $containerPath

$result = aws batch register-job-definition --job-definition-name $JobName --type container --platform-capabilities FARGATE --container-properties "file://$containerPath" --region $Region --profile $Profile --output json | ConvertFrom-Json
Assert-Last "Registrar definición"
$revision = $result.revision
Write-Host "[6/6] Definición registrada: ${JobName}:$revision" -ForegroundColor Green
Write-Host "Imagen: ${ecr}@${digest}"
Write-Host "El Scheduler existente permanece sin cambios (DISABLED)."
Write-Host "Usa la revisión ${JobName}:$revision en el script ejecutar_fase8.ps1."
