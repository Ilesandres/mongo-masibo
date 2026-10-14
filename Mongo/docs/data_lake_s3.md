# Data Lake en la nube (Amazon S3)

Este documento describe cómo el Data Lake de Hyperflix pasa de **carpetas en el
disco local** (`Mongo/data_lake/raw|processed|curated`) a un **almacenamiento de
objetos real en la nube** (Amazon S3 u otro servicio S3-compatible como MinIO),
**sin reescribir los pipelines**.

- Código: `Mongo/almacenamiento.py` (abstracción local/S3) + `config.py` (credenciales).
- Pipeline afectado: `Mongo/scripts/data_lake_pipeline.py` (Fase 6) y las salidas de
  `Mongo/scripts/spark_jobs.py` (Fase 8).
- Script de migración: `Mongo/scripts/subir_data_lake_s3.py`.

---

## 1. ¿Por qué migrar?

| Carpeta local (laboratorio) | Amazon S3 (enterprise) |
| --- | --- |
| Limitada por el disco del PC | Almacenamiento prácticamente **infinito** |
| Se pierde si falla la máquina | **Durabilidad 99,999999999%** (11 nueves) |
| Acoplada a la computación (mismo equipo) | **Separada** de la computación (se escala aparte) |
| No accesible por varios consumidores | Acceso concurrente (Spark, Athena, BI) |
| Copias de seguridad manuales | Versionado y ciclo de vida por política |

Un Data Lake real **no es una carpeta en un PC**: es almacenamiento de objetos
duradero, elástico y desacoplado. S3 es el mismo destino al que apuntarían Kafka
→ Spark en un entorno de producción.

---

## 2. Arquitectura: una sola línea de código, dos backends

```
                        .env → DATA_LAKE_BACKEND
                                  │
             ┌────────────────────┴────────────────────┐
             ▼                                          ▼
      local (por defecto)                              s3
  Mongo/data_lake/{raw,processed,curated}/   s3://{S3_BUCKET}/{S3_PREFIX}/{zona}/
             │                                          │
             └───────────── Mongo/almacenamiento.py ────┘
                                    │
                        data_lake_pipeline.py · spark_jobs.py
```

`almacenamiento.py` decide si una escritura va al disco o a la nube. El pipeline
sigue escribiendo `df.to_parquet(...)`, pero en modo S3 la ruta es
`s3://bucket/zona/archivo.parquet` (gestionada con `s3fs`).

```
MongoDB  →  Python/Pandas  →  Parquet (Snappy)  →  local  ó  s3://bucket/...
```

---

## 3. Requisitos y credenciales

### 3.1 Cuenta de AWS (Free Tier)

El *Free Tier* de AWS incluye **5 GB de S3 gratis durante 12 meses**. Para un
laboratorio como Hyperflix es más que suficiente.

### 3.2 Crear el bucket

Desde la consola (S3 → *Create bucket*) o con la AWS CLI:

```bash
aws s3 mb s3://abp-data-lake-andresiles --region us-east-2
```

> El nombre del bucket es **globalmente único**. Si `abp-data-lake-...` ya está
> tomado, usa otro (p. ej. `abp-data-lake-tu-nombre`).

### 3.3 Usuario IAM y política mínima

No uses el usuario *root* de AWS. Crea un usuario IAM (p. ej. `script-s3-user`)
con una **política mínima** sobre tu bucket:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "LeerBucket",
      "Effect": "Allow",
      "Action": ["s3:ListBucket", "s3:GetBucketLocation"],
      "Resource": "arn:aws:s3:::abp-data-lake-andresiles"
    },
    {
      "Sid": "ObjetosDelLake",
      "Effect": "Allow",
      "Action": ["s3:PutObject", "s3:GetObject", "s3:DeleteObject"],
      "Resource": "arn:aws:s3:::abp-data-lake-andresiles/*"
    }
  ]
}
```

Genera un **Access key** (Access Key ID + Secret Access Key). Esas dos claves son
las que van al `.env`.

---

## 4. Configuración (`.env`)

El `.env` real que lee `config.py` es `taller-conexion-mongo/.env` (no versionado).
Añade/descomenta el bloque:

```ini
# Data Lake: local | s3
DATA_LAKE_BACKEND=s3

S3_BUCKET=abp-data-lake-andresiles
S3_PREFIX=hyperflix
AWS_REGION=us-east-2
AWS_ACCESS_KEY_ID=AKIA...
AWS_SECRET_ACCESS_KEY=...
```

| Variable | ¿Obligatoria? | Descripción |
| --- | --- | --- |
| `DATA_LAKE_BACKEND` | Sí (para S3) | `local` (por defecto) o `s3` |
| `S3_BUCKET` | Sí | Nombre del bucket |
| `S3_PREFIX` | No | Carpeta raíz dentro del bucket (ej. `hyperflix`). Vacío = raíz |
| `AWS_REGION` | Recomendada | Región del bucket (ej. `us-east-1`, `us-east-2`). **Debe coincidir** con la del bucket |
| `AWS_ACCESS_KEY_ID` | Sí | Access Key ID del usuario IAM |
| `AWS_SECRET_ACCESS_KEY` | Sí | Secret Access Key |
| `AWS_SESSION_TOKEN` | **No** | Solo si usas credenciales **temporales** (STS/rol/MFA). Con un usuario IAM normal va vacío |
| `S3_ENDPOINT_URL` | **No** | Solo para S3-compatibles (MinIO, Spaces...). Para AWS real va vacío |

> La plantilla versionada es `.env.example`. Copia los valores y rellénalos.

---

## 5. Uso

```bash
# Fase 6 — el pipeline escribe DIRECTAMENTE en S3 (si DATA_LAKE_BACKEND=s3)
python Mongo/scripts/data_lake_pipeline.py

# Fase 8 — los resultados de Spark también se suben a S3
python Mongo/scripts/spark_jobs.py
```

### Migrar los Parquet que ya tengas en disco

Si primero corriste el pipeline en modo `local`, sube lo ya generado sin
recalcular nada:

```bash
python Mongo/scripts/subir_data_lake_s3.py
```

Sube `Mongo/data_lake/**/*.parquet` respetando la estructura de zonas
(incluida `curated/spark/`).

---

## 6. Verificación

```bash
# Listar el contenido del lake en S3
aws s3 ls s3://abp-data-lake-andresiles/hyperflix/ --recursive
```

El resumen final de la Fase 6 indica el backend y el destino:

```
--- Bloque 7. Resumen del Data Lake (backend: s3) ---
  RAW: 10 archivo(s) | ...
  PROCESSED: 6 archivo(s) | ...
  CURATED: 9 archivo(s) | ...
```

Rutas esperadas: `s3://abp-data-lake-andresiles/hyperflix/raw/usuarios.parquet`, etc.

---

## 7. Costos (Free Tier)

| Concepto | Free Tier (12 meses) | Al terminar |
| --- | --- | --- |
| Almacenamiento | 5 GB | ~USD 0,023/GB/mes |
| Peticiones PUT | 2.000/mes | ~USD 0,005/1.000 |
| Peticiones GET | 20.000/mes | ~USD 0,0004/1.000 |
| Transferencia salida | 100 GB/mes | ~USD 0,09/GB |

Un Data Lake de laboratorio (~0,1–1 GB) entra sobradamente en el Free Tier.
**Recomendación:** configura una *lifecycle rule* y borra el bucket al terminar
la práctica si no lo necesitas.

---

## 8. Alternativa local: MinIO (S3-compatible)

El `docker-compose.infra.yml` del proyecto ya levanta **MinIO** en
`http://localhost:9000` como espejo S3 del Data Lake. Para usarlo:

```ini
DATA_LAKE_BACKEND=s3
S3_BUCKET=hyperflix-lake
S3_PREFIX=hyperflix
AWS_REGION=us-east-1
AWS_ACCESS_KEY_ID=hyperflix_admin
AWS_SECRET_ACCESS_KEY=cambia-este-password-min12
S3_ENDPOINT_URL=http://localhost:9000
```

Con `S3_ENDPOINT_URL` definido, `almacenamiento.py` activa automáticamente el
**direccionamiento por ruta** (`addressing_style: path`), que MinIO exige.

---

## 9. Del laboratorio a producción

| Laboratorio (este repo) | Producción |
| --- | --- |
| `Mongo/data_lake/raw` | `s3://bucket/raw/` |
| `Mongo/data_lake/processed` | `s3://bucket/processed/` |
| `Mongo/data_lake/curated` | `s3://bucket/curated/` |
| `df.to_parquet("data_lake/...")` | `df.to_parquet("s3://bucket/...")` |
| Pandas + PyArrow | Spark + Delta/Iceberg sobre S3 |
| PC único | Almacenamiento desacoplado del cómputo |

---

## 10. Solución de problemas

| Síntoma | Causa probable | Solución |
| --- | --- | --- |
| `Access Denied` al firmar | `AWS_REGION` mal escrita (p. ej. `region=us-east-2`) o distinta a la del bucket | Escribe solo la región (`us-east-2`) y verifica con `aws s3api get-bucket-location --bucket ...` |
| `Access Denied` en listados | Falta `s3:ListBucket` en la política IAM | Añade el permiso al recurso del bucket |
| `NoSuchBucket` | El bucket no existe o el nombre/región no coinciden | Crea el bucket en la región correcta |
| `InvalidAccessKeyId` / `SignatureDoesNotMatch` | Claves mal copiadas | Regenera la access key y vuelve a pegar en el `.env` |
| `ModuleNotFoundError: s3fs` | Falta la dependencia | `pip install -r requirements.txt` |
| Timeout en MinIO | Falta `S3_ENDPOINT_URL` | Definir el endpoint local |
