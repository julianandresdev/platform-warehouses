
param(
    [string]$Date = (
        [DateTime]::UtcNow.AddHours(-5).Date.AddDays(-1).ToString("yyyy-MM-dd")
    ),
    [Parameter(Mandatory = $true)]
    [string]$JobDefinition,
    [string]$Profile = "PerfilUniversidad",
    [string]$Region = "us-east-1",
    [string]$Bucket = "warehouse-platform-santi-2026"
)

$ErrorActionPreference = "Stop"

$env:AWS_PROFILE = $Profile
$env:AWS_DEFAULT_REGION = $Region
$env:REPORT_BUCKET = $Bucket
$env:BATCH_REGISTRY_BACKEND = "s3"

Remove-Item Env:BATCH_DATABASE_URL -ErrorAction SilentlyContinue
Remove-Item Env:S3_ENDPOINT_URL -ErrorAction SilentlyContinue


function Assert-Last($descripcion) {
    if ($LASTEXITCODE -ne 0) {
        throw "$descripcion fallo (codigo $LASTEXITCODE)"
    }
}


# ========================================
# VALIDACIONES INICIALES
# ========================================

$day = [DateTime]::MinValue

if (-not [DateTime]::TryParseExact(
    $Date,
    "yyyy-MM-dd",
    [System.Globalization.CultureInfo]::InvariantCulture,
    [System.Globalization.DateTimeStyles]::None,
    [ref]$day
)) {
    throw "Fecha invalida: $Date. Usa YYYY-MM-DD"
}

if ($JobDefinition -notmatch '^warehouse-platform-inventory:\d+$') {
    throw "Debes indicar una revision concreta de AWS Batch"
}

if (-not (Test-Path "services/batch/exportar_movimientos.py")) {
    throw "Ejecuta este script desde la raiz de platform-warehouses"
}

$awsPath = Join-Path $env:USERPROFILE ".aws"

if (-not (Test-Path $awsPath)) {
    throw "No se encontro la carpeta de credenciales AWS"
}


# ========================================
# 1. VERIFICAR AWS Y REGISTRO S3
# ========================================

Write-Host "[1/6] Revisando AWS y registro de fecha $Date..."

aws sts get-caller-identity `
    --profile $Profile `
    --query Account `
    --output text

Assert-Last "Verificacion AWS"

$runKey = "batch-runs/$Date.json"
$tmpRun = Join-Path $env:TEMP "warehouse-run-$Date.json"

# Buscar el registro sin generar un error 404.
$existingKey = aws s3api list-objects-v2 `
    --bucket $Bucket `
    --prefix $runKey `
    --max-keys 1 `
    --query "Contents[0].Key" `
    --output text `
    --region $Region `
    --profile $Profile

Assert-Last "Consultar registro S3"

$existingKey = "$existingKey".Trim()

if ($existingKey -eq $runKey) {

    aws s3api get-object `
        --bucket $Bucket `
        --key $runKey `
        $tmpRun `
        --region $Region `
        --profile $Profile `
        --output json | Out-Null

    Assert-Last "Descargar registro S3"

    $run = Get-Content $tmpRun -Raw |
        ConvertFrom-Json

    if ($run.status -eq "SUCCEEDED") {
        throw "La fecha $Date ya fue procesada correctamente"
    }

    if ($run.status -eq "RUNNING") {
        throw "La fecha $Date tiene una ejecucion activa o pendiente de recuperacion"
    }

    if ($run.status -ne "FAILED") {
        throw "Estado inesperado: $($run.status)"
    }

    Write-Host "Registro FAILED encontrado. Se permite reintentar."
}
else {
    Write-Host "No existe registro previo. Se permite procesar la fecha."
}


# ========================================
# 2. VERIFICAR REDES DOCKER
# ========================================

Write-Host "[2/6] Comprobando redes de PostgreSQL..."

$redes = @(
    "compose_wh001",
    "compose_wh002",
    "compose_wh003"
)

foreach ($red in $redes) {

    docker network inspect $red `
        --format '{{.Name}}' | Out-Null

    Assert-Last "Verificar red Docker $red"
}

$dbPassword = if ($env:DB_PASSWORD) {
    $env:DB_PASSWORD
}
else {
    "localdev"
}

# Codificar la contrasena para las URL PostgreSQL.
$dbPasswordUrl = [System.Uri]::EscapeDataString($dbPassword)

$container = "warehouse-export-$Date-" +
    [guid]::NewGuid().ToString("N").Substring(0, 8)


# ========================================
# 3. EXPORTAR MOVIMIENTOS
# ========================================

Write-Host "[3/6] Exportando las tres bodegas a S3..."

try {

    docker create `
        --name $container `
        --network compose_wh001 `
        --mount "type=bind,source=$awsPath,target=/root/.aws,readonly" `
        -e "AWS_PROFILE=$Profile" `
        -e "AWS_DEFAULT_REGION=$Region" `
        -e "REPORT_BUCKET=$Bucket" `
        -e "WH001_DATABASE_URL=postgresql+psycopg2://admin:${dbPasswordUrl}@wh001_db:5432/platform" `
        -e "WH002_DATABASE_URL=postgresql+psycopg2://admin:${dbPasswordUrl}@wh002_db:5432/platform" `
        -e "WH003_DATABASE_URL=postgresql+psycopg2://admin:${dbPasswordUrl}@wh003_db:5432/platform" `
        --entrypoint python `
        warehouse-batch:local `
        exportar_movimientos.py --date $Date | Out-Null

    Assert-Last "Crear contenedor exportador"

    docker network connect compose_wh002 $container
    Assert-Last "Conectar WH-002"

    docker network connect compose_wh003 $container
    Assert-Last "Conectar WH-003"

    docker start -a $container
    Assert-Last "Iniciar exportador"

    $exitCode = (
        docker inspect $container `
            --format '{{.State.ExitCode}}'
    ).Trim()

    Assert-Last "Consultar estado del exportador"

    if ($exitCode -ne "0") {
        throw "El exportador fallo con codigo $exitCode"
    }

    Write-Host "Exportacion completada correctamente."
}
finally {

    docker rm -f $container 2>$null | Out-Null
}



# ========================================
# 4. VALIDAR MANIFIESTO S3
# ========================================

Write-Host "[4/6] Validando manifiesto y archivos CSV..."

$validate = @'
import sys
import boto3
from datetime import date

sys.path.insert(0, "services/batch")

from main import validar_manifiesto

cliente = boto3.client("s3")

validar_manifiesto(
    cliente,
    sys.argv[1],
    date.fromisoformat(sys.argv[2])
)

print("MANIFIESTO VALIDADO")
'@

$validatePath = Join-Path $env:TEMP "warehouse-validar-manifiesto.py"

[System.IO.File]::WriteAllText(
    $validatePath,
    $validate,
    [System.Text.UTF8Encoding]::new($false)
)

python $validatePath $Bucket $Date

Assert-Last "Validar manifiesto"

Write-Host "Integridad de archivos confirmada."

# ========================================
# 5. ENVIAR TRABAJO A AWS BATCH
# ========================================

Write-Host "[5/6] Enviando trabajo a AWS Batch Fargate..."

$overridePath = Join-Path $env:TEMP `
    "warehouse-overrides-$Date.json"

$overrides = @{
    command = @(
        "python",
        "main.py",
        "--date",
        $Date
    )
}

$overrides |
    ConvertTo-Json -Compress |
    Set-Content -Path $overridePath -Encoding ascii

$jobId = aws batch submit-job `
    --job-name "warehouse-daily-$($Date.Replace('-', ''))" `
    --job-queue warehouse-platform-queue `
    --job-definition $JobDefinition `
    --container-overrides "file://$overridePath" `
    --region $Region `
    --profile $Profile `
    --query jobId `
    --output text

Assert-Last "Enviar trabajo a AWS Batch"

$jobId = "$jobId".Trim()

if ($jobId -notmatch '^[0-9a-f-]{36}$') {
    throw "AWS devolvio un Job ID invalido: $jobId"
}


# ========================================
# 6. RESULTADO Y SEGUIMIENTO
# ========================================

Write-Host ""
Write-Host "[6/6] Trabajo enviado correctamente" `
    -ForegroundColor Green

Write-Host "JOB ID: $jobId"
Write-Host "Fecha: $Date"
Write-Host "Definicion: $JobDefinition"

Write-Host ""
Write-Host "Consultar estado del trabajo:"

Write-Host "aws batch describe-jobs --jobs $jobId --region $Region --profile $Profile --query `"jobs[].{Estado:status,Razon:statusReason}`" --output json"

Write-Host ""
Write-Host "IMPORTANTE:"
Write-Host "El trabajo fue enviado, pero todavia debe terminar en SUCCEEDED."
Write-Host "EventBridge Scheduler sigue desactivado."
Write-Host "La exportacion utiliza PostgreSQL local en Docker."
