# Infraestructura como Código (IaC) — Hyperflix

## 1. ¿Qué es y cómo se aplica?

**Infraestructura como Código (IaC)** consiste en gestionar y aprovisionar la infraestructura tecnológica (servidores, bases de datos, redes, contenedores, almacenamiento) mediante **archivos de configuración legibles y versionados**, en lugar de crearla manualmente haciendo clic en consolas web o comandos ad-hoc.

En Hyperflix esto significa que todo el entorno — **Replica Set de MongoDB, almacenamiento de objetos compatible con S3 (MinIO), clúster MongoDB Atlas en la nube y carpetas del Data Lake** — se define y despliega a partir de código, garantizando que cualquier máquina reproduzca exactamente el mismo ambiente.

## 2. Herramientas seleccionadas

| Herramienta | Rol en Hyperflix |
| --- | --- |
| **Docker Compose** (`docker-compose.infra.yml`) | Orquestación y aprovisionamiento local: MongoDB configura en **Replica Set `rs0`** (3 nodos), inicializado automáticamente por `rs_setup`, y **MinIO** como espejo S3 del Data Lake. Redes virtuales aisladas + volúmenes persistentes. |
| **Terraform** (`infra/terraform/`) | Aprovisionamiento reproducible en la nube con el proveedor **`mongodb/mongodbatlas`**: crea el proyecto, el clúster (M0 por defecto, escalable a M10) y el usuario de base de datos, y expone la URI de conexión. |
| **Orquestador** (`deploy_infra.ps1`) | **Un solo comando hace TODO**: la parte local y la nube, en orden. Todo el resultado se muestra en la terminal y además queda en un log (`logs/infra_<fecha>.log`). |
| **Script local** (`deploy_infra_local.ps1`) | Parte local: valida Docker, despliega el compose, espera el estado *healthy* y la inicialización de la réplica, aparta la estructura del Data Lake y prepara el venv. |
| **Script nube** (`deploy_infra_nube.ps1`) | Parte nube: `terraform init` → `plan` → `apply` en MongoDB Atlas y muestra los outputs (incluida la URI). |
| **Config como Código** (`iac_setup.py`) | Bootstrap del entorno local con UN comando: valida Python ≥ 3.12, crea/valida el `.venv`, instala dependencias, provisiona el Data Lake y hace health check a Atlas (con `.env.template` si falta el `.env`). |

## 3. Estructura de archivos

```
├── docker-compose.infra.yml        # IaC local: Replica Set MongoDB rs0 + MinIO
├── deploy_infra.ps1                # Orquestador: 1 comando para TODO (local + nube)
├── deploy_infra_local.ps1          # Script IaC de la parte LOCAL (Docker + MinIO)
├── deploy_infra_nube.ps1           # Script IaC de la parte NUBE (Terraform Atlas)
├── iac_setup.py                    # Config como Código: bootstrap del entorno local
├── .env.infra.example              # Plantilla de secretos del compose (NO se suben credenciales)
├── logs/                           # Logs generados por los scripts (no versionado)
└── infra/terraform/
    ├── main.tf                     # Recursos Atlas: proyecto, clúster, DB user
    ├── variables.tf                # Variables tipadas (defaults para M0 / AWS / US_EAST_1)
    ├── outputs.tf                  # Salidas: project_id y mongo_uri_srv (URI para config.py)
    └── terraform.tfvars.example    # Plantilla de credenciales (el real NO se versiona)
```

## 4. Cómo se despliega

Cada script (`deploy_infra_local.ps1` y `deploy_infra_nube.ps1`) es ejecutable por sí solo; el orquestador los invoca en cadena. **El resultado siempre se muestra en la terminal y se escribe en `logs/`** (un archivo por ejecución del orquestador).

### 4.1 Infraestructura local (Replica Set + MinIO)

Con Docker Desktop activo:

```powershell
Copy-Item .env.infra.example .env.infra      # 1. definir credenciales de MinIO
.\deploy_infra_local.ps1                      # 2. despliega y espera healthy + rs.initiate
```

O manualmente:

```powershell
docker compose -f docker-compose.infra.yml up -d          # levanta nodos + MinIO
docker compose -f docker-compose.infra.yml up rs_setup    # inicializa el Replica Set (rs0)
```

El **`rs_setup`** ejecuta `rs.initiate()` con tres miembros (`mongodb_primary`, `mongodb_secondary` y `mongodb_arbiter`), de modo que el Replica Set queda operativo y **MongoDB Change Streams (Fase 7) puede usarse en local**. Está aislado en el perfil `rs-init`, así que `docker compose up -d` no lo dispara por accidente; si ya se inicializó al re-desplegar (los volúmenes persisten), reporta `already initialized` y el estado de los 3 miembros — operación idempotente.

**Detener (teardown):**

```powershell
.\deploy_infra.ps1 -Down           # apaga contenedores + red, conserva los datos
.\deploy_infra.ps1 -Down -Volumes  # además BORRA los volúmenes (datos RS y MinIO)
# equivalente manual: docker compose -f docker-compose.infra.yml down [-v]
```

Con `-Down` pide confirmación antes de actuar; `-Volumes` es destructivo (elimina los datos persistentes del Replica Set y de MinIO).

### 4.2 Nube (MongoDB Atlas) con Terraform

```powershell
Copy-Item infra\terraform\terraform.tfvars.example infra\terraform\terraform.tfvars
# editar terraform.tfvars con las llaves de la API de Atlas (nivel ORGANIZACIÓN)
.\deploy_infra_nube.ps1                # init + plan + apply en Atlas (crea proyecto + clúster M0 + usuario)
# (o manual: terraform -chdir=infra\terraform init && apply)
```

El output `mongo_uri_srv` es la URI SRV que va en `.env` como `MONGO_URI` (leída por `config.py`).

### 4.3 Reproducibilidad completa (un solo comando)

```powershell
.\deploy_infra.ps1                 # TODO: local (data lake + Docker + venv) + nube (Atlas)
.\deploy_infra.ps1 -SoloLocal      # solo la parte local        (equiv.: .\deploy_infra_local.ps1)
.\deploy_infra.ps1 -SoloNube       # solo la parte nube         (equiv.: .\deploy_infra_nube.ps1)
```

Toda la salida del despliegue queda registrada en `logs\infra_<fecha>.log` además de mostrarse en la terminal.

### 4.4 Configuración como Código — `iac_setup.py`

Bootstrap del entorno local con un solo comando (sin Docker ni Terraform):

```powershell
py iac_setup.py
```

1. **Valida Python ≥ 3.12** (muestra la versión detectada).
2. **Valida/instala el `.venv`**: crea el entorno virtual si falta y verifica que su versión sea ≥ 3.12 (si es vieja, alerta y lo recrea).
3. **Verifica/instala dependencias**: `pip install -r requirements.txt` + `pip check` (consistencia).
4. **Provisiona el Data Lake**: `Mongo/data_lake/{raw,processed,curated,curated/spark}`.
5. **Valida el `.env`** de `taller-conexion-mongo/` (el que usa `config.py`) y su `MONGO_URI`. **Si falta:** genera un `.env.template` en la raíz con datos de ejemplo y muestra WARNING/ALERTA (en ese caso no valida la conexión).
6. **Health Check MongoDB Atlas**: `ping` con timeout corto; imprime SOLO el host de la URI (nunca credenciales).

Resumen final `✓/✗` por fase y exit code 0/1.

## 5. Qué garantiza esta implementación

- **Reproducibilidad:** un solo comando levanta el ambiente completo; no hay pasos manuales documentados por aparte (y cada parte tiene su propio script).
- **Configuración como Código:** `iac_setup.py` prepara el entorno local (Python/venv/dependencias/Data Lake) y valida `.env` + conexión a Atlas, con alertas claras si falta algo (incluido generar `.env.template`).
- **Trazabilidad:** cada ejecución genera un log en `logs/` (ruta, comando y resultado), además de la salida en terminal.
- **Secrets por separado:** ni el compose ni el Terraform llevan credenciales hardcodeadas (`.env.infra` y `terraform.tfvars` están en `.gitignore`; solo se versionan sus plantillas).
- **Salud verificable:** healthchecks con `mongosh ping` y espera activa del estado *healthy* y de la inicialización de la réplica antes de continuar.
- **Escalado:** el mismo Terraform pasa de `M0` (gratuito/local de pruebas) a `M10` cambiando una variable.
- **Replica Set funcional:** indispensable para la Fase 7 (Change Streams = CDC), cubierta en local sin depender del tier de Atlas.