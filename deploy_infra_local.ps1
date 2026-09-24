<#
.SYNOPSIS
  Despliegue de la infraestructura LOCAL (Docker + MinIO) — Hyperflix IaC.
.DESCRIPTION
  Automatiza la parte local del entorno de forma reproducible:
    1. Crea la estructura del data lake (Mongo/data_lake/{raw,processed,curated,spark}).
    2. Levanta el Replica Set de MongoDB (rs0) + MinIO vía docker-compose.infra.yml.
    3. Espera el estado healthy de los 3 nodos + inicialización de la réplica (rs_setup).
    4. (Opcional) Preparar .venv e instalar requirements.
  En modo -Down detiene (o borra con -Volumes) la infraestructura local.
  El detalle se muestra en la terminal y se guarda en un archivo de log (logs/).
.EXAMPLE
  .\deploy_infra_local.ps1                 # despliega local (data lake + Docker + venv)
  .\deploy_infra_local.ps1 -SkipDocker     # solo estructura del data lake + venv
  .\deploy_infra_local.ps1 -SkipEnv        # sin venv/requirements
  .\deploy_infra_local.ps1 -Down           # apaga contenedores + red (datos seguros)
  .\deploy_infra_local.ps1 -Down -Volumes  # BORRA los volumenes persistentes
#>
[CmdletBinding()]
param(
    [switch]$SkipDocker,
    [switch]$SkipEnv,
    [switch]$Down,
    [switch]$Volumes,
    [string]$LogFile = ""
)

$ErrorActionPreference = "Stop"
$root = $PSScriptRoot

if (-not $LogFile) {
    $LogFile = Join-Path $root "logs\infra_local_$(Get-Date -Format 'yyyyMMdd_HHmmss').log"
}
New-Item -ItemType Directory -Path (Split-Path $LogFile) -Force | Out-Null

# Registra en el log y muestra en la terminal al mismo tiempo.
function Escribir-Log {
    param(
        [string]$Mensaje,
        [string]$Color = "Gray"
    )
    $linea = "[$(Get-Date -Format 'HH:mm:ss')] $Mensaje"
    Add-Content -Path $LogFile -Value $linea -Encoding UTF8
    if (-not $Color -or $Color -eq "Gray") { Write-Host $Mensaje } else { Write-Host $Mensaje -ForegroundColor $Color }
}

# Ejecuta un comando nativo (docker) de forma segura bajo
# $ErrorActionPreference="Stop": baja la política solo durante el comando,
# deja que el stderr fluya a la consola y devuelve el exit code real.
function Invoke-Nativo {
    param([string]$Comando)
    $ea = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        Invoke-Expression $Comando | ForEach-Object { Escribir-Log $_ }
        return $LASTEXITCODE
    }
    finally {
        $ErrorActionPreference = $ea
    }
}

# ── Modo teardown local ──
if ($Down) {
    Escribir-Log "=== Deteniendo Infraestructura LOCAL (Hyperflix IaC) ===" "Cyan"
    if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
        Escribir-Log "[ERROR] Docker no esta instalado o no esta en el PATH." "Red"
        exit 1
    }
    $compose = "docker compose -f `"$(Join-Path $root "docker-compose.infra.yml")`""
    $detalle = "apaga los contenedores y la red (los datos persisten en los volumenes)"
    $flag = ""
    if ($Volumes) {
        $detalle = "apaga todo y BORRA los volumenes persistentes (datos del RS y MinIO incluidos)"
        $flag = " -v"
    }
    if ($env:HYPERFLIX_SIN_CONFIRMAR -ne "1") {
        $resp = Read-Host "`nSe ${detalle}. Continuar? (s/N)"
        if ($resp -notmatch "^(s|si|y|yes)$") {
            Escribir-Log "  Cancelado por el usuario. Nada se detuvo." "Yellow"
            exit 0
        }
    }
    $codigo = Invoke-Nativo "$compose down$flag"
    if ($codigo -ne 0) { Escribir-Log "[ERROR] Fallo al detener la infraestructura local." "Red"; exit 1 }
    Escribir-Log "=== Infraestructura LOCAL detenida exitosamente ===" "Green"
    exit 0
}

Escribir-Log "=== Despliegue LOCAL (Docker + MinIO) - Hyperflix IaC ===" "Cyan"
Escribir-Log "Log: $LogFile"

# 1. Estructura del data lake (idempotente)
Escribir-Log "[1/4] Preparando estructura del Data Lake..." "Yellow"
$dataLake = Join-Path $root "Mongo\data_lake"
foreach ($zona in @("raw", "processed", "curated", "curated\spark")) {
    $dir = Join-Path $dataLake $zona
    if (-not (Test-Path $dir)) {
        New-Item -ItemType Directory -Path $dir -Force | Out-Null
        Escribir-Log "  [OK] $zona"
    }
    else {
        Escribir-Log "  [--] $zona (ya existe)"
    }
}

# 2. Docker Compose (Replica Set MongoDB + MinIO)
if (-not $SkipDocker) {
    Escribir-Log "[2/4] Validando Docker..." "Yellow"
    if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
        Escribir-Log "[ERROR] Docker no esta instalado o no esta en el PATH." "Red"
        exit 1
    }
    $compose = "docker compose -f `"$(Join-Path $root "docker-compose.infra.yml")`""
    $codigo = Invoke-Nativo 'docker version --format "Server: {{.Server.Version}}"'
    if ($codigo -ne 0) {
        Escribir-Log "[ERROR] Docker no esta corriendo. Inicia Docker Desktop." "Red"
        exit 1
    }
    Escribir-Log "  [OK] Docker activo"

    Escribir-Log "[3/4] Desplegando contenedores, redes y volumenes persistentes..." "Yellow"
    $codigo = Invoke-Nativo "$compose up -d"
    if ($codigo -ne 0) { Escribir-Log "[ERROR] Fallo al levantar docker compose." "Red"; exit 1 }

    Escribir-Log "  Esperando arranque de los nodos del Replica Set (healthchecks)..." "Yellow"
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
            Escribir-Log "[ERROR] El nodo $nodo no llego a healthy a tiempo." "Red"
            exit 1
        }
        Escribir-Log "  [OK] $nodo healthy"
    }

    Escribir-Log "  Inicializando el Replica Set (rs_init => rs.initiate)..." "Yellow"
    $codigo = Invoke-Nativo "$compose up rs_setup"
    if ($codigo -ne 0) { Escribir-Log "  [AVISO] rs_setup no termino con codigo 0 (si ya estaba inicializado, es normal)." "Yellow" }
    Escribir-Log "  Estado del Replica Set:"
    Invoke-Nativo "$compose ps"
}

# 4. venv + dependencias (opcional)
if (-not $SkipEnv -and -not $SkipDocker) {
    Escribir-Log "[4/4] Preparando entorno Python (.venv + requirements)..." "Yellow"
    $venvPython = Join-Path $root ".venv\Scripts\python.exe"
    if (-not (Test-Path $venvPython)) {
        Escribir-Log "  [+] Creando entorno virtual (.venv)..." "Yellow"
        python -m venv (Join-Path $root ".venv")
    }
    Escribir-Log "  [+] Instalando dependencias (requirements.txt)..." "Yellow"
    & $venvPython -m pip install -r (Join-Path $root "requirements.txt")
    if ($LASTEXITCODE -ne 0) { Escribir-Log "[ERROR] No se pudieron instalar las dependencias." "Red"; exit 1 }
}

Escribir-Log "=== Infraestructura LOCAL desplegada exitosamente ===" "Green"