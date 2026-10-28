# CI/CD (DataOps) con GitHub Actions — Hyperflix

> **Para el informe:** «Implementación de un pipeline de CI/CD (DataOps) con GitHub Actions para garantizar la entrega continua y la validación automática de la infraestructura (Terraform → MongoDB Atlas) y del código de procesamiento (Python: Data Lake y Data Warehouse)».

## 1. ¿Por qué?

El proyecto ya tenía **Infraestructura como Código** (Terraform, Docker Compose, scripts `.ps1`) y un código de procesamiento grande (Fases 1-10). Pero todo se ejecutaba **a mano**, desde un PC, y nada impedía subir un cambio que rompiera el ETL o el Terraform.

El siguiente paso lógico en DevOps/DataOps es **automatizar la ejecución**: cada `git push` dispara un pipeline que valida el código y la infraestructura y, si todo está bien, despliega.

| Antes (manual) | Ahora (CI/CD) |
| --- | --- |
| `.\deploy_infra_nube.ps1` desde un PC | `terraform plan/apply` en GitHub Actions |
| El estado de Terraform vive en un solo disco | Estado remoto en **S3** con bloqueo (`use_lockfile`) |
| Sin pruebas: los errores se veían al ejecutar | **27 pruebas** (`pytest`) en cada push/PR |
| Cualquiera aplicaba cambios a la nube | `apply` solo en `main` y con **aprobación manual** |

## 2. Arquitectura del pipeline

Archivo: [`.github/workflows/deploy.yml`](../../.github/workflows/deploy.yml)

```
 git push / pull request a main
            │
   ┌────────┴─────────┐
   ▼                  ▼
🧪 Pruebas Python   🔎 Terraform fmt + validate     ← CI (siempre, sin credenciales)
   └────────┬─────────┘
            ▼
     📋 Terraform plan                              ← solo si existe el secret TF_STATE_BUCKET
            │   (resumen del plan en la pestaña Summary)
            ▼
     🚀 Desplegar (terraform apply)                 ← solo push a main
            │   + aprobación manual del environment "produccion"
            ▼
     MongoDB Atlas (proyecto + clúster + usuario)
```

| Job | Cuándo corre | Qué hace |
| --- | --- | --- |
| `pruebas-python` | push y PR | Instala `requirements.txt` + `requirements-dev.txt`, compila todos los scripts (`compileall`) y corre `pytest`. Publica `reporte-pruebas.xml` como artefacto. |
| `terraform-validar` | push y PR | `terraform fmt -check`, `init -backend=false` y `validate`. No necesita credenciales. |
| `nube-configurada` | push y PR | Revisa si existe el secret `TF_STATE_BUCKET` (GitHub no permite usar `secrets` en el `if:` de un job) y deja `activo=true/false`. |
| `terraform-plan` | push y PR, **si** `nube-configurada` dio `activo=true` | Configura el estado remoto en S3, ejecuta `terraform plan -detailed-exitcode` y lo resume en el *Summary* del run. |
| `desplegar` | solo **push a `main`** + aprobación | Vuelve a planear y ejecuta `terraform apply`; muestra los outputs (proyecto, clúster, tier). |

**Seguridad por diseño:**
- Sin el secret `TF_STATE_BUCKET`, el pipeline hace solo CI (pruebas + validación) y **nunca toca la nube**.
- Las pruebas fuerzan `DATA_LAKE_BACKEND=local` y `DW_BACKEND=none`: no usan S3, BigQuery ni MongoDB.
- Los secretos viven en **GitHub Secrets**, nunca en el repositorio.
- `permissions: contents: read` (mínimo privilegio) y `concurrency` para que dos despliegues no choquen sobre el mismo estado.

## 3. Pruebas automáticas (`tests/`)

| Archivo | Qué valida |
| --- | --- |
| `test_config.py` | Coherencia de `config.py`: índices sobre colecciones existentes, tablas DW iguales a la Fase 9, umbrales ordenados. |
| `test_models.py` | Reglas de negocio de `Mongo/models/`: códigos deterministas, emails únicos, `valor = minutos × tarifa`, progreso ≤ 100 %, "Completada" ⇒ minutos = duración. |
| `test_almacenamiento.py` | Abstracción local ↔ S3: rutas `s3://bucket/prefijo/zona/...`, error claro sin bucket, **región mal escrita** (incidente de la Sesión 20), MinIO con *path-style*, ida y vuelta de Parquet. |
| `test_dw_cloud.py` | Capa DW: apagada por defecto, `tabla_id`, detección de **BigQuery Sandbox** y elección de la partición (incidente de la Sesión 22: en sandbox → por ingesta). |
| `test_pipeline_e2e.py` | **Prueba de humo de punta a punta:** genera un Data Lake sintético mínimo (RAW → PROCESSED → CURATED) en una carpeta temporal y verifica que el ETL de la Fase 10 produce `dim_tiempo`, `dim_cliente`, `dim_pelicula` y `fact_consumo` coherentes. |

Correrlas en el PC (no tocan tu Data Lake real ni la nube):

```powershell
.\.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
python -m pytest
```

## 4. Configuración en GitHub (una sola vez)

### 4.1 Solo CI (pruebas + validación)
No hace falta configurar nada: al subir `.github/workflows/deploy.yml` el pipeline corre en cada push/PR.

### 4.2 Despliegue continuo (plan + apply en Atlas)

**Paso 1 — Migrar el estado de Terraform a S3.** Hoy el estado vive en `infra/terraform/terraform.tfstate` (local). Si GitHub Actions corriera `apply` sin ese estado, intentaría **crear de nuevo** el proyecto y el clúster. Por eso hay que subirlo primero (se reutiliza el bucket del Data Lake):

```powershell
cd infra/terraform
# Archivo temporal SOLO para migrar (está en .gitignore; bórralo al terminar)
@'
terraform {
  backend "s3" {
    bucket       = "abp-data-lake-andresiles"
    key          = "hyperflix/terraform/terraform.tfstate"
    region       = "us-east-2"
    encrypt      = true
    use_lockfile = true
  }
}
'@ | Set-Content -Encoding utf8 backend_override.tf
terraform init -migrate-state      # responde "yes": copia el estado local a S3
Remove-Item backend_override.tf    # el PC vuelve a usar su estado local
```

> ⚠️ Desde ese momento la **fuente de verdad** es el estado en S3. Si vuelves a usar `deploy_infra_nube.ps1` en el PC, el estado local puede quedar desactualizado; lo recomendable es desplegar solo desde el pipeline.

**Paso 2 — Secrets** (*Settings → Secrets and variables → Actions → Secrets*):

| Secret | Valor |
| --- | --- |
| `ATLAS_ORG_ID` | `org_id` de tu `terraform.tfvars` |
| `ATLAS_PUBLIC_KEY` | `mongodbatlas_public_key` |
| `ATLAS_PRIVATE_KEY` | `mongodbatlas_private_key` |
| `ATLAS_DB_PASSWORD` | `db_password` |
| `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` | Credenciales IAM con acceso al bucket del estado |

**Paso 3 — Resto de la configuración, también como Secrets.** El workflow busca cada valor primero en *Secrets*, luego en *Variables* y, si no está, usa el valor por defecto:

| Secret | Valor | ¿Obligatorio? |
| --- | --- | --- |
| `TF_STATE_BUCKET` | `abp-data-lake-andresiles` | **Sí** (activa plan/apply) |
| `AWS_REGION` | `us-east-2` | No (por defecto `us-east-2`) |
| `TF_STATE_KEY` | `hyperflix/terraform/terraform.tfstate` | No |
| `TF_PROJECT_NAME` / `TF_CLUSTER_NAME` | `Hyperflix-IaC` / `Cluster-IaC` | No (por defecto, los nombres ya creados) |
| `TF_CLUSTER_TIER` / `TF_PROVIDER_REGION` | `M0` / `US_EAST_1` | No |

> Los nombres **deben coincidir** con lo que ya existe en Atlas; si no, el `plan` propondrá renombrar o recrear recursos.

**Paso 4 — Environment con aprobación** (*Settings → Environments → New environment* → `produccion` → *Required reviewers*: tu usuario). Así el `apply` espera tu clic de aprobación.

**Paso 5 — Política IAM:** además de los permisos del Data Lake (ver [`data_lake_s3.md`](data_lake_s3.md)), el usuario necesita `s3:GetObject`, `s3:PutObject`, `s3:DeleteObject` sobre `hyperflix/terraform/*` (el `DeleteObject` es para el archivo de bloqueo `.tflock`) y `s3:ListBucket` sobre el bucket.

## 5. Flujo de trabajo resultante

1. Creas una rama y haces un cambio (p. ej. `cluster_tier = "M10"` o un ajuste del ETL).
2. Abres un **pull request** → corren las pruebas, la validación y el `plan`; el resumen muestra qué cambiaría en Atlas.
3. Haces **merge a `main`** → se repite la validación y el job `desplegar` queda **esperando aprobación**.
4. Apruebas → `terraform apply` → la infraestructura en la nube queda igual al código.

## 6. Troubleshooting

| Síntoma | Causa / solución |
| --- | --- |
| Plan y Desplegar salen *skipped* | Falta el secret `TF_STATE_BUCKET` (comportamiento esperado: solo CI); el job `¿Nube configurada?` lo avisa. |
| `terraform fmt` falla | Ejecuta `terraform fmt -recursive` en `infra/terraform` y vuelve a subir. |
| El plan quiere **crear** el proyecto/clúster | El estado no se migró a S3 (Paso 1) o `TF_STATE_KEY` apunta a otra ruta. |
| `AccessDenied` en `init` | Faltan permisos IAM sobre el bucket/clave del estado (Paso 5) o región incorrecta. |
| `401` / `403` de Atlas | API key sin rol a nivel organización o la IP de GitHub no está en la *API Access List* de la key (desactívala o usa una key sin restricción de IP). |
