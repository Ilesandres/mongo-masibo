<#
.SYNOPSIS
  Despliegue de la infraestructura EN LA NUBE (MongoDB Atlas + Terraform) — Hyperflix IaC.
.DESCRIPTION
  Automatiza la parte cloud del entorno de forma reproducible:
    1. Localiza el binario de Terraform (PATH o WinGet).
    2. terraform init (instala el provider mongodb/mongodbatlas).
    3. terraform plan -out=tfplan (revisa los cambios antes de aplicar).
    4. terraform apply tfplan (crea: proyecto, clúster M0 gratis y usuario de BD).
    5. Muestra los outputs (project_id, cluster, tier y mongo_uri_srv).
  Configuración en infra/terraform/terraform.tfvars (NO versionado: credenciales).
  El detalle se muestra en la terminal y se guarda en un archivo de log (logs/).
.EXAMPLE
  .\deploy_infra_nube.ps1               # init + plan + apply en MongoDB Atlas
  .\deploy_infra_nube.ps1 -LogFile x    # escribe el detalle en el log indicado
#>
[CmdletBinding()]
param(
    [string]$LogFile = ""
)

$ErrorActionPreference = "Stop"
$root = $PSScriptRoot
$TerraformDir = Join-Path $root "infra\terraform"

try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch {}

if (-not $LogFile) {
    $LogFile = Join-Path $root "logs\infra_nube_$(Get-Date -Format 'yyyyMMdd_HHmmss').log"
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

# Ejecuta un comando nativo (terraform) de forma segura bajo
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

# Localiza el ejecutable de terraform: PATH primero, luego la instalación de WinGet.
function Find-Terraform {
    $cmd = Get-Command terraform -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    $winGetLinks = Join-Path $env:LOCALAPPDATA "Microsoft\WinGet\Links\terraform.exe"
    if (Test-Path $winGetLinks) { return $winGetLinks }
    $pkg = Get-ChildItem (Join-Path $env:LOCALAPPDATA "Microsoft\WinGet\Packages\Hashicorp.Terraform*\terraform.exe") -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($pkg) { return $pkg.FullName }
    return $null
}

Escribir-Log ""
Escribir-Log "  ╔═══════════════════════════════════════════════════════════╗" "Magenta"
Escribir-Log "  ║   ☁️  HYPERFLIX · NUBE COMO CÓDIGO (TERRAFORM · ATLAS)  ☁️  ║" "Cyan"
Escribir-Log "  ║   Proyecto · Clúster M0 · Usuario BD · URI de conexión    ║" "Cyan"
Escribir-Log "  ╚═══════════════════════════════════════════════════════════╝" "Magenta"
Escribir-Log "  Log del resultado: $LogFile" "DarkGray"
Escribir-Log "Log: $LogFile"

$terraform = Find-Terraform
if (-not $terraform) {
    Escribir-Log "[ERROR] terraform no esta instalado. Instalalo con: winget install Hashicorp.Terraform" "Red"
    exit 1
}
Escribir-Log "[+] Terraform: $terraform"

if (-not (Test-Path (Join-Path $TerraformDir "terraform.tfvars"))) {
    Escribir-Log "[ERROR] Falta $TerraformDir\terraform.tfvars (copia terraform.tfvars.example y llena org_id + API keys + db_password)." "Red"
    exit 1
}

pushd $TerraformDir
try {
    $codigo = Invoke-Nativo "& `"$terraform`" init -input=false"
    if ($codigo -ne 0) { Escribir-Log "[ERROR] terraform init fallo." "Red"; exit 1 }

    Escribir-Log "[+] Calculando plan de cambios (terraform plan)..." "Yellow"
    $codigo = Invoke-Nativo "& `"$terraform`" plan -input=false -out=tfplan"
    if ($codigo -ne 0) { Escribir-Log "[ERROR] terraform plan fallo." "Red"; exit 1 }

    Escribir-Log "[+] Aplicando plan (terraform apply). Clúster M0 gratuito: puede tardar varios minutos..." "Yellow"
    $codigo = Invoke-Nativo "& `"$terraform`" apply `"tfplan`""
    if ($codigo -ne 0) { Escribir-Log "[ERROR] terraform apply fallo." "Red"; exit 1 }

    Escribir-Log "`n[+] Outputs de Atlas (proyecto/clúster/URI):" "Green"
    Invoke-Nativo "& `"$terraform`" output"
}
finally {
    popd
}

Escribir-Log "=== Infraestructura NUBE aplicada exitosamente ===" "Green"
Escribir-Log "Para conectar la app, copia el mongo_uri_srv como MONGO_URI en tu .env (y ajusta el Access List de Atlas con tu IP)."