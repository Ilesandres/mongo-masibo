# Data Warehouse en la nube (Fase 10) — BigQuery / Snowflake

> Guía de la **Fase 10**: cómo el modelo estrella construido en las Fases 6 y 9
> se replica en un **Data Warehouse real de la nube** (OLAP), sin romper ningún
> flujo existente.

---

## 1. ¿Por qué migrar el DW a la nube?

En la arquitectura moderna, la base de datos transaccional y el Data Warehouse
son **sistemas separados**:

| Capa | Rol | Herramienta en este proyecto |
| --- | --- | --- |
| **OLTP** — escribir rápido, transacciones | Ingesta y operación | **MongoDB Atlas** (Fases 1-5, 7) |
| **Data Lake** — volumen barato, formatos abiertos | Staging / históricos | **Parquet en disco o Amazon S3** (Fases 6, 8) |
| **OLAP** — leer y analizar rápido | Analítica, BI, reportes | **Snowflake / BigQuery / Redshift** (Fase 10) |

MongoDB es excelente para **escribir** (Fase 9 ya construyó un prototipo de
Star Schema dentro de la misma BD), pero un DW en la nube está diseñado para
**leer y analizar a gran escala**: columnar, particionado, con escalado
elástico y costo por consulta. La **Fase 9 sigue viva**: sirve como prototipo
local y como línea base del benchmark comparativo.

```
   MongoDB Atlas (OLTP)            Data Lake                Data Warehouse (OLAP)
 ┌──────────────────────┐   ┌──────────────────────┐   ┌──────────────────────────┐
 │ Fases 1-5: estructura│   │ Fase 6: RAW/PROCESSED│   │ Fase 10: dim_tiempo      │
 │ datos masivos, ETL   │──▶│ /CURATED (Parquet)   │──▶│      dim_cliente         │
 │ Fase 7: Change Streams│  │ Fase 8: Spark Jobs   │   │      dim_pelicula        │
 └──────────────────────┘   │ (disco o S3)         │   │      fact_consumo        │
          │                 └──────────────────────┘   │  + partición y clustering│
          │                          │                 └──────────────────────────┘
          ▼                          │                              │
 ┌──────────────────────┐            │                              ▼
 │ Fase 9: DW prototipo │            │                     Looker Studio / SQL /
 │ dentro de MongoDB     │            └───────────────────▶ benchmark comparativo
 └──────────────────────┘
```

**Regla de oro de esta fase:** la integración es **aditiva**. Con
`DW_BACKEND=none` (el valor por defecto) el proyecto se comporta **exactamente
igual que antes**; nada de lo nuevo se ejecuta.

---

## 2. Elección de plataforma (gratis)

| Criterio | **Google BigQuery (Sandbox)** | **Snowflake (Free Trial)** |
| --- | --- | --- |
| Tarjeta de crédito | **No pide** | Sí (USD 400 / 30 días) |
| Vigencia | Permanente (cuota mensual gratis) | 30 días |
| Cuota gratis | 10 GB de almacenamiento + 1 TB de consultas/mes | USD 400 de crédito |
| Carga desde S3 | Vía Python (`load_table_from_dataframe`) | Directa (external stage + `COPY INTO`) |
| Dashboard | **Looker Studio** (gratis) | Looker Studio / Tableau |
| Estado en este repo | **Implementado y es el principal** | Implementado (ruta alternativa, no probada aún) |

Con ~5M de hechos el `fact_consumo` ocupa unos pocos cientos de MB: **cabe con
creces en la cuota gratuita** de BigQuery.

> ⚠️ **Restricción clave del Sandbox (sin facturación):** Google **impone** que
> toda tabla y toda partición expire en **≤ 60 días** y **no permite quitarlo**
> (la API responde *"Table expiration time must be less than 60 days while in
> sandbox mode"*). Consecuencias y mitigaciones de este proyecto:
>
> 1. **Particionar por fecha de negocio no sirve en sandbox**: las particiones
>    con más de 60 días se ocultan/borran **apenas se cargan** (se perdió 82% de
>    una carga de prueba: 1.000 filas → 178 visibles). Por eso el ETL detecta el
>    sandbox y usa **partición por fecha de ingestión** (`_PARTITIONTIME`): los
>    60 días corren desde la carga. La fecha de negocio queda en el *clustering*
>    (`fecha_id`, `cliente_id`, `pelicula_id`, `dispositivo`), así que las
>    consultas por rango de fechas siguen siendo rápidas.
> 2. **Las tablas `dim_*` expiran 60 días después de crearse** → se restauran
>    re-ejecutando el ETL (`--modo replace`, idempotente).
> 3. **Ruta permanente:** habilitar la *facturación* en el proyecto (tarjeta)
>    desactiva el sandbox: entonces el ETL vuelve solo a particionar por
>    `fecha_id` (`DW_PARTICION_MODO=auto`) y los datos dejan de expirar. Con las
>    guardas de costo (`BQ_MAX_BYTES_BILLED` + cuota gratis de 1 TB/mes) el gasto
>    real estimado sigue siendo **≈ USD 0**.

---

## 3. Arquitectura del código

| Archivo | Rol |
| --- | --- |
| `Mongo/dw_cloud.py` | **Abstracción del DW** (patrón de `almacenamiento.py`): conexión, dataset, carga de DataFrames, consultas con guardia de costo y cierre. Import protegido de las librerías opcionales. |
| `Mongo/scripts/data_warehouse_cloud.py` | **ETL (Fase 10)**: lee la zona CURATED → transforma al esquema de la Fase 9 → carga al DW. |
| `config.py` (bloque DW) | `DW_BACKEND`, `BQ_*`, `SNOWFLAKE_*`, `TABLAS_DW_NUBE`, `DW_PARTICION`, `DW_CLUSTER`. |
| `requirements-dw.txt` | Dependencias **opcionales** (`google-cloud-bigquery`, `db-dtypes`). A propósito no están en `requirements.txt`: sin ellas nada falla. |

### Mapeo CURATED → tablas del DW (mismos nombres que la Fase 9)

| Zona CURATED (Fase 6) | Tabla del DW (Fase 9) | Transformación clave |
| --- | --- | --- |
| `fact_reproduccion` | `fact_consumo` | `usuario_id → cliente_id`, `fecha_id` (DATE) desde `dim_fecha`, claves sustitutas y medidas |
| `dim_fecha` | `dim_tiempo` | + `fin_semana` (ISO: 6=sábado, 7=domingo) |
| `dim_usuario` | `dim_cliente` | + `segmento` (misma regla `config.SEGMENTO_*`) y métricas: `reproducciones`, `minutos_totales`, `gasto_total`, `valor_promedio` |
| `dim_pelicula` | `dim_pelicula` | + `reproducciones`, `minutos_totales`, `ingresos_totales` |

> **Nota de consistencia:** en la Fase 9 `dim_tiempo.dia_semana` usa la
> convención de MongoDB (`$dayOfWeek`: domingo = 1) y en la Fase 10 la ISO
> (`pandas.dayofweek`: lunes = 1). En ambas `fin_semana` marca sábado/domingo.

### Garantías de no-regresión

1. **Cero ediciones** a los scripts de las Fases 1-9 (solo se agregó el bloque DW en `config.py`).
2. `DW_BACKEND=none` por defecto → la capa está **apagada** y el flujo actual no cambia.
3. El ETL **solo lee** el Data Lake; **nunca escribe en MongoDB**.
4. Cargas idempotentes por defecto (`--modo replace`, equivalente al `$merge` de la Fase 4).
5. Secretos solo en `.env` (gitignored). El JSON de la service account también está en `.gitignore` (`*-credentials.json`).
6. Guardia de costo: `BQ_MAX_BYTES_BILLED` + **dry-run** antes de la consulta de validación.

---

## 4. Puesta en marcha (BigQuery, gratis)

1. **Activar la Sandbox** en [console.cloud.google.com](https://console.cloud.google.com) → BigQuery → *Try BigQuery free* (no pide tarjeta).
2. **Service account**: IAM & Admin → Service Accounts → crear → roles
   `BigQuery Data Editor` y `BigQuery Job User` → generar clave JSON (clave del JSON, tipo *Google Cloud Platform key*).
3. **Configurar el `.env`** (`taller-conexion-mongo/.env`):

```ini
DW_BACKEND=bigquery
BQ_PROJECT=mi-proyecto-gcp
BQ_DATASET=hyperflix
BQ_LOCATION=US
BQ_MAX_BYTES_BILLED=1073741824      # 1 GB por consulta: techo de gasto
GOOGLE_APPLICATION_CREDENTIALS=C:\ruta\credenciales-dw.json
```

4. **Instalar la dependencia opcional**: `pip install -r requirements-dw.txt`

---

## 5. Comandos

```bash
# 1) Validar TODO el ETL sin conexión a la nube (sin credenciales ni librerías)
python Mongo/scripts/data_warehouse_cloud.py --solo-validar

# 2) Primera corrida real: solo 1.000 filas (smoke test barato)
python Mongo/scripts/data_warehouse_cloud.py --limite 1000

# 3) Carga completa (sobrescribe las 4 tablas; idempotente)
python Mongo/scripts/data_warehouse_cloud.py

# 4) Carga incremental (agrega filas nuevas; útil con --modo append)
python Mongo/scripts/data_warehouse_cloud.py --modo append
```

| Argumento | Por defecto | Descripción |
| --- | --- | --- |
| `--modo {replace,append}` | `replace` | `replace` sobrescribe (idempotente); `append` agrega filas |
| `--limite N` | sin límite | recorta el hecho a N filas para pruebas |
| `--solo-validar` | desactivado | lee y transforma el Data Lake **sin** tocar la nube |

---

## 6. Modelo físico en el DW (particionamiento)

`fact_consumo` se carga con partición diaria **+** clustering. El modo lo decide
`DW_PARTICION_MODO` (config) con la detección automática de sandbox:

| `DW_PARTICION_MODO` | Partición | Cuándo se usa |
| --- | --- | --- |
| `auto` (**por defecto**) | sandbox → **ingestación**; con facturación → `fecha_id` | decide solo, según el dataset |
| `ingesta` | `_PARTITIONTIME` (fecha de carga) | proyecto **Sandbox** (retención 60 días) |
| `fecha` | `fecha_id` (fecha de negocio) | proyecto **con facturación habilitada** |

- **Partición** → BigQuery escanea solo las particiones necesarias en lugar de
  la tabla completa (en sandbox, la de ingestión evita que los datos cargados
  hoy desaparezcan por tener fecha antigua).
- **`CLUSTER BY fecha_id, cliente_id, pelicula_id, dispositivo`** (con
  partición de ingestión) → la fecha de negocio queda agrupada, de modo que los
  filtros por rango de fechas de las 10 consultas del benchmark siguen
  acelerándose por *cluster pruning*.

Si el esquema de partición de la tabla existente no coincide con el deseado,
BigQuery no permite cambiarlo en caliente: el ETL **recrea la tabla** (solo con
`--modo replace`, que la iba a sobrescribir de todos modos).

En Snowflake la partición se traduce a *clustering keys* / `AUTO_CLUSTERING`
(el backend es experimental y aún no se ha probado en este repo).

---

## 7. Benchmark comparativo (siguiente paso)

La idea es correr las **mismas 10 consultas** de `benchmarking_consultas.py`
(Fase 5) traducidas a Standard SQL y comparar latencias:

| Consulta | MongoDB (ms) | BigQuery (ms) |
| --- | --- | --- |
| 1. Reproducciones y minutos mensuales | pendiente | pendiente |
| … | … | … |

Con eso se cierra el argumento del entregable: **MongoDB escribe rápido (OLTP),
el DW de la nube lee rápido (OLAP)**, y el data lake es el puente entre ambos.

---

## 8. Costos y troubleshooting

- **Costo esperado ≈ USD 0**: `BQ_MAX_BYTES_BILLED` + dry-run + cuota gratis de 1 TB/mes.
- `Falta la librería 'google-cloud-bigquery'` → `pip install -r requirements-dw.txt`.
- `Falta BQ_PROJECT en el .env` → rellenar `BQ_PROJECT`.
- `No se encontraron credenciales de Google` → revisar `GOOGLE_APPLICATION_CREDENTIALS` o correr `gcloud auth application-default login`.
- `No se encontró 'fact_reproduccion.parquet'` → ejecutar la Fase 6 o `generar_data_lake_sintetico.py` (la fuente es el Data Lake, no MongoDB).
- **`Table expiration time must be less than 60 days while in sandbox mode`** / **`Billing has not been enabled for this project`** → el proyecto está en **Sandbox**: Google obliga a expirar en ≤60 días y no deja quitar la expiración. Solución adoptada: partición por **ingestación** (automática en `DW_PARTICION_MODO=auto`). *No es un error de `pagos` ni de los datos.*
- **La tabla `fact_consumo` tiene menos filas de las cargadas** → casi siempre son particiones ya expiradas por el sandbox (consulta `MIN(fecha_id)`; si coincide con *hoy − 60 días*, es esto). Recarga con `--modo replace`.
- **`bigquery.datasets.update denied`** → el rol *BigQuery Data Editor* de la service account no administra datasets (solo tablas). Con el sandbox tampoco sirve: la expiración es de Google. No hace falta ningún rol extra para este proyecto.
- **`Changing the partitioning scheme of an existing table is not allowed`** → corre con `--modo replace` (el ETL recrea la tabla automáticamente).
- **`Permission denied` / `403`** → revisar los roles de la service account: `BigQuery Data Editor` + `BigQuery Job User` son suficientes.
- Las tablas `dim_*` **expiran 60 días después de crearse** (sandbox) → vuelve a correr el ETL antes de esa fecha (es idempotente).
- **Los datos no llegan a BigQuery** → revisar el job en *BigQuery → Execution history* (el mensaje de error de Google incluye la causa exacta).
