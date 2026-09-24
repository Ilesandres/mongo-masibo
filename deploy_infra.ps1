<#
.SYNOPSIS
  Despliegue INFRAESTRUCTURA COMO CÓDIGO (IaC) — Hyperflix. UN solo comando hace TODO.
.DESCRIPTION
  Orquestador de la infraestructura. Por defecto ejecuta la parte LOCAL
  (Docker + MinIO, vía deploy_infra_local.ps1) y la parte NUBE (MongoDB Atlas
  con Terraform, vía deploy_infra_nube.ps1), en ese orden.
  El resultado completo se muestra en la terminal y se guarda en logs/infra_<fecha>.log.
.EXAMPLE
  .\deploy_infra.ps1                     # TODO: local (Docker) + nube (Terraform Atlas)
  .\deploy_infra.ps1 -SoloLocal          # solo infraestructura local
  .\deploy_infra.ps1 -SoloNube           # solo infraestructura en la nube (Atlas)
  .\deploy_infra.ps1 -SkipEnv            # local sin venv/requirements
  .\deploy_infra.ps1 -Down               # detiene lo local (apaga contenedores + red)
  .\deploy_infra.ps1 -Down -Volumes      # lo mismo y BORRA los volumenes persistentes
.NOTES
  También existen los scripts individuales: .\deploy_infra_local.ps1 y .\deploy_infra_nube.ps1
#>
[CmdletBinding()]
param(
    [switch]$SoloLocal,
    [switch]$SoloNube,
    [switch]$SkipEnv,
    [switch]$Down,
    [switch]$Volumes
)

$ErrorActionPreference = "Stop"
$root = $PSScriptRoot

if ($SoloLocal -and $SoloNube) {
    Write-Error "[ERROR] Usa -SoloLocal o -SoloNube, no ambos."
    exit 1
}

$LogFile = Join-Path $root "logs\infra_$(Get-Date -Format 'yyyyMMdd_HHmmss').log"
New-Item -ItemType Directory -Path (Split-Path $LogFile) -Force | Out-Null

function Escribir-Titulo {
    param([string]$Texto)
    Write-Host ""
    Write-Host ("=" * 66) -ForegroundColor Cyan
    Write-Host $Texto -ForegroundColor Cyan
    Write-Host ("=" * 66) -ForegroundColor Cyan
}

Write-Host "`n=== Hyperflix IaC - INFRAESTRUCTURA COMO CÓDIGO ===" -ForegroundColor Cyan
Write-Host "      Log del resultado: $LogFile"
Write-Host "        (y en la terminal)   `n" -ForegroundColor DarkGray

# ── Teardown local: detiene (o borra) la infraestructura local ──
if ($Down) {
    $env:HYPERFLIX_SIN_CONFIRMAR = "1"
    try {
        if ($Volumes) {
            & (Join-Path $root "deploy_infra_local.ps1") -Down -Volumes
        }
        else {
            & (Join-Path $root "deploy_infra_local.ps1") -Down
        }
    }
    finally {
        Remove-Item Env:HYPERFLIX_SIN_CONFIRMAR -ErrorAction SilentlyContinue
    }
    exit $LASTEXITCODE
}

# ── Despliegue: local y/o nube según flags ──
if (-not $SoloNube) {
    Escribir-Titulo " 1/2  LOCAL  (Docker Replica Set + MinIO)  "
    if ($SkipEnv) {
        & (Join-Path $root "deploy_infra_local.ps1") -LogFile $LogFile -SkipEnv
    }
    else {
        & (Join-Path $root "deploy_infra_local.ps1") -LogFile $LogFile
    }
    if ($LASTEXITCODE -ne 0) {
        Write-Host "[ERROR] La fase LOCAL fallo. Detalle completo en el log." -ForegroundColor Red
        exit 1
    }
}

if (-not $SoloLocal) {
    Write-Host -NoNewline "" # (separador visual)
    Write-Host ""
    Escribir-Titulo " 2/2  NUBE  (MongoDB Atlas con Terraform)  "
    & (Join-Path $root "deploy_infra_nube.ps1") -LogFile $LogFile
    if ($LASTEXITCODE -ne 0) {
        Write-Host "[ERROR] La fase NUBE fallo. Detalle completo en el log." -ForegroundColor Red
        exit 1
    }
}

Write-Host "`n=== INFRAESTRUCTURA COMPLETA desplegada correctamente ===" -ForegroundColor Green
Write-Host "      Log: $LogFile" -ForegroundColor DarkGray