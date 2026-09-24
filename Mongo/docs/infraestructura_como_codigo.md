# Infraestructura como Código (IaC) — Hyperflix

## 1. ¿Qué es y cómo se aplica?

**Infraestructura como Código (IaC)** consiste en gestionar y aprovisionar la infraestructura tecnológica (servidores, bases de datos, redes, contenedores, almacenamiento) mediante **archivos de configuración legibles y versionados**, en lugar de crearla manualmente haciendo clic en consolas web o comandos ad-hoc.

En Hyperflix esto significa que todo el entorno — **Replica Set de MongoDB, almacenamiento de objetos compatible con S3 (MinIO), clúster MongoDB Atlas en la nube y carpetas del Data Lake** — se define y despliega a partir de código, garantizando que cualquier máquina reproduzca exactamente el mismo ambiente.

## 2. Herramientas seleccionadas

| Herramienta | Rol en Hyperflix |
| --- | --- |
| **Docker Compose** (`docker-compose.infra.yml`) | Orquestación y aprovisionamiento local: MongoDB configura en **Replica Set `rs0`** (3 nodos), inicializado automáticamente por `rs_setup`, y **MinIO** como espejo S3 del Data Lake. Redes virtuales aisladas + volúmenes persistentes. |
| **Terraform** (`infra/terraform/`) | Aprovisionamiento reproducible en la nube con el proveedor **`mongodb/mongodbatlas`**: crea el proyecto, el clúster (M0 por defecto, escalable a M10) y el usuario de base de datos, y expone la URI de conexión. |
| **Script de automatización** (`deploy_infra.ps1`) | Comando único que valida Docker, despliega el compose, espera el estado *healthy* y la inicialización de la réplica, aparta la estructura del Data Lake y (opcional) ejecuta Terraform y prepara el venv. |

## 3. Estructura de archivos

```
├── docker-compose.infra.yml        # IaC local: Replica Set MongoDB rs0 + MinIO
├── deploy_infra.ps1                # Script de automatización (PowerShell)
├── .env.infra.example              # Plantilla de secretos del compose (NO se suben credenciales)
└── infra/terraform/
    ├── main.tf                     # Recursos Atlas: proyecto, clúster, DB user
    ├── variables.tf                # Variables tipadas (defaults para M0 / AWS / US_EAST_1)
    ├── outputs.tf                  # Salidas: project_id y mongo_uri_srv (URI para config.py)
    └── terraform.tfvars.example    # Plantilla de credenciales (el real NO se versiona)
```

## 4. Cómo se despliega

### 4.1 Infraestructura local (Replica Set + MinIO)

Con Docker Desktop activo:

```powershell
Copy-Item .env.infra.example .env.infra      # 1. definir credenciales de MinIO
.\deploy_infra.ps1                            # 2. despliega y espera healthy + rs.initiate
```

O manualmente:

```powershell
docker compose -f docker-compose.infra.yml up -d
```

El **`rs_setup`** ejecuta `rs.initiate()` con tres miembros (`mongodb_primary`, `mongodb_secondary` y `mongodb_arbiter`), de modo que el Replica Set queda operativo y **MongoDB Change Streams (Fase 7) puede usarse en local**.

### 4.2 Nube (MongoDB Atlas) con Terraform

```powershell
Copy-Item infra\terraform\terraform.tfvars.example infra\terraform\terraform.tfvars
# editar terraform.tfvars con las llaves de la API de Atlas
.\deploy_infra.ps1 -Terraform                # o: terraform init && terraform apply -auto-approve
```

El output `mongo_uri_srv` es la URI SRV que va en `.env` como `MONGO_URI` (leída por `config.py`).

### 4.3 Reproducibilidad completa

```powershell
.\deploy_infra.ps1 -Terraform                # estructura + docker + Atlas + venv
```

## 5. Qué garantiza esta implementación

- **Reproducibilidad:** un solo comando levanta el ambiente completo; no hay pasos manuales documentados por aparte.
- **Secrets por separado:** ni el compose ni el Terraform llevan credenciales hardcodeadas (`.env.infra` y `terraform.tfvars` están en `.gitignore`; solo se versionan sus plantillas).
- **Salud verificable:** healthchecks con `mongosh ping` y espera activa del estado *healthy* y de la inicialización de la réplica antes de continuar.
- **Escalado:** el mismo Terraform pasa de `M0` (gratuito/local de pruebas) a `M10` cambiando una variable.
- **Replica Set funcional:** indispensable para la Fase 7 (Change Streams = CDC), cubierta en local sin depender del tier de Atlas.