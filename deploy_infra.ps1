<#
.SYNOPSIS
  Despliegue de Infraestructura como Código (IaC) — Hyperflix.
.DESCRIPTION
  Automatiza el aprovisionamiento del entorno de forma reproducible:
    1. Crea la estructura del data lake (Mongo/data_lake/{raw,processed,curated,spark}).
    2. Levanta el Replica Set de MongoDB (rs0) + MinIO vía docker-compose.infra.yml.
    3. Espera el estado healthy de Mongo + la inicialización de la réplica (rs_setup).
    4. (Opcional) Aprovisiona MongoDB Atlas con Terraform (infra/terraform).
    5. (Opcional) Prepara el venv e instala requirements.
.EXAMPLE
  .\deploy_infra.ps1                    # Docker + estructura del data lake
  .\deploy_infra.ps1 -Terraform         # incluye Terraform apply
  .\deploy_infra.ps1 -SkipDocker        # solo estructura + venv
#>
[CmdletBinding()]
param(
    [switch]$SkipDocker,
    [switch]$Terraform,
    [switch]$SkipEnv,
    [string]$TerraformDir = "$PSScriptRoot\infra\terraform"
)

$ErrorActionPreference = "Stop"
$root = $PSScriptRoot

# Ejecuta un comando nativo (docker/terraform) de forma segura bajo
# $ErrorActionPreference="Stop": baja la política solo durante el comando,
# deja que el stderr fluya a la consola y devuelve el exit code real.
function Invoke-Nativo {
    param([string]$Comando)
    $ea = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        Invoke-Expression $Comando | ForEach-Object { Write-Host $_ }
        return $LASTEXITCODE
    }
    finally {
        $ErrorActionPreference = $ea
    }
}

Write-Host "`n=== Iniciando Despliegue de Infraestructura como Codigo (IaC) - Hyperflix ===" -ForegroundColor Cyan

# 1. Estructura del data lake (idempotente)
Write-Host "`n[1/4] Preparando estructura del Data Lake..." -ForegroundColor Yellow
$dataLake = Join-Path $root "Mongo\data_lake"
foreach ($zona in @("raw", "processed", "curated", "curated\spark")) {
    $dir = Join-Path $dataLake $zona
    if (-not (Test-Path $dir)) {
        New-Item -ItemType Directory -Path $dir -Force | Out-Null
        Write-Host "  [OK] $zona"
    }
    else {
        Write-Host "  [--] $zona (ya existe)"
    }
}

# 2. Docker Compose (Replica Set MongoDB + MinIO)
if (-not $SkipDocker) {
    Write-Host "`n[2/4] Validando Docker..." -ForegroundColor Yellow
    if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
        Write-Error "[ERROR] Docker no esta instalado o no esta en el PATH."
        exit 1
    }
    $compose = "docker compose -f `"$(Join-Path $root "docker-compose.infra.yml")`""
    $codigo = Invoke-Nativo "docker version --format 'Server: {`{.Server.Version`}'"
    if ($codigo -ne 0) {
        Write-Error "[ERROR] Docker no esta corriendo. Inicia Docker Desktop."
        exit 1
    }
    Write-Host "  [OK] Docker activo"

    Write-Host "`n[3/4] Desplegando contenedores, redes y volumenes persistentes..." -ForegroundColor Yellow
    $codigo = Invoke-Nativo "$compose up -d"
    if ($codigo -ne 0) { Write-Error "[ERROR] Fallo al levantar docker compose."; exit 1 }

    Write-Host "`n  Esperando arranque de los nodos del Replica Set (healthchecks)..." -ForegroundColor Yellow
    $nodos = @("mongo_primary", "mongo_secondary", "mongo_arbiter")
    $espera_maxima = 180
    foreach ($nodo in $nodos) {
        $ok = $false
        for ($i = 0; $i -lt $espera_maxima; $i += 10) {
            $estado = docker inspect --format "{{.State.Health.Status}}" $nodo 2>$null
            if ($estado -eq "healthy") { $ok = $true; break }
            Start-Sleep -Seconds 10
        }
        if (-not $ok) {
            Write-Error "[ERROR] El nodo $nodo no llego a healthy a tiempo."
            exit 1
        }
        Write-Host "  [OK] $nodo healthy"
    }

    Write-Host "`n  Inicializando el Replica Set (rs_init => rs.initiate)..." -ForegroundColor Yellow
    $codigo = Invoke-Nativo "$compose up rs_setup"
    if ($codigo -ne 0) { Write-Warning "  [AVISO] rs_setup no termino con codigo 0 (si ya estaba inicializado, es normal)." }
    Write-Host "`n  Estado del Replica Set:"
    Invoke-Nativo "$compose ps"
}

# 4. Terraform (opcional)
if ($Terraform) {
    Write-Host "`n[4/4] Aprovisionando MongoDB Atlas con Terraform..." -ForegroundColor Yellow
    if (-not (Get-Command terraform -ErrorAction SilentlyContinue)) {
        Write-Error "[ERROR] terraform no esta instalado."
        exit 1
    }
    pushd $TerraformDir
    try {
        terraform init -input=false
        if ($LASTEXITCODE -ne 0) { throw "terraform init fallo" }
        terraform apply -auto-approve
        if ($LASTEXITCODE -ne 0) { throw "terraform apply fallo" }
        Write-Host "`n  [OK] Atlas aprovisionado. Usa el output mongo_uri_srv en .env (MONGO_URI)." -ForegroundColor Green
    }
    finally {
        popd
    }
}

# 5. venv + dependencias (opcional)
if (-not $SkipEnv) {
    $venvPython = Join-Path $root ".venv\Scripts\python.exe"
    if (-not (Test-Path $venvPython)) {
        Write-Host "`n[+] Creando entorno virtual (.venv)..." -ForegroundColor Yellow
        python -m venv (Join-Path $root ".venv")
    }
    Write-Host "`n[+] Instalando dependencias (requirements.txt)..." -ForegroundColor Yellow
    & $venvPython -m pip install -r (Join-Path $root "requirements.txt")
    if ($LASTEXITCODE -ne 0) { Write-Error "[ERROR] No se pudieron instalar las dependencias."; exit 1 }
}

Write-Host "`n=== Infraestructura desplegada exitosamente ===" -ForegroundColor Green