import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / "taller-conexion-mongo" / ".env")


def _entero(valor, por_defecto):
    """Convierte un valor de .env a int de forma segura (basura → por defecto)."""
    try:
        return int(valor)
    except (TypeError, ValueError):
        return por_defecto


MONGO_URI = os.getenv("MONGO_URI") or os.getenv("mongo_uri")
DB_NAME = os.getenv("DB_NAME") or os.getenv("db_name") or "hyperflix_BD"

# ── Colecciones ────────────────────────────────────────────
COLECCIONES_OLTP = [
    "generos",
    "directores",
    "planes",
    "usuarios",
    "peliculas",
    "suscripciones",
    "pagos",
    "resenas",
    "reproducciones",
]
COLECCION_OLAP = "reproducciones_analiticas"
COLECCIONES_DATALAKE = COLECCIONES_OLTP + [COLECCION_OLAP]

# Data Warehouse (modelo estrella en MongoDB, Fase 9)
COLECCIONES_DW = ["dim_tiempo", "dim_cliente", "dim_pelicula", "fact_consumo"]

# ── Volúmenes de generación masiva (a gran escala) ─────────
NUM_GENEROS = 8
NUM_DIRECTORES = 500
NUM_PLANES = 3
NUM_USUARIOS = 120_000
NUM_PELICULAS = 6_000
NUM_SUSCRIPCIONES = 180_000
NUM_PAGOS = 600_000
NUM_RESENAS = 250_000
NUM_REPRODUCCIONES = 5_000_000
BATCH_SIZE = 2_000

# ── Reglas de negocio / analítica ──────────────────────────
TARIFA_POR_MINUTO = 1000
MARGEN_GANANCIA = 0.15
SEGMENTO_COMPLETO_MIN = 90_000
SEGMENTO_PARCIAL_MIN = 30_000
MINUTOS_MARATON = 120  # alerta en streaming: película larga completada en una sola sesión

# ── Segmentación de clientes (Spark Job 2) ───────────────
SEGMENTO_VIP_MIN = 10_000_000
SEGMENTO_PREMIUM_MIN = 2_000_000
SEGMENTO_FRECUENTE_MIN = 500_000

# ── Apache Spark ──────────────────────────────────────────
SPARK_APP_NAME = "Hyperflix-BigData"

# ── Data Lake ──────────────────────────────────────────────
DATA_LAKE_ROOT = Path(__file__).resolve().parent / "Mongo" / "data_lake"
ZONAS_DATALAKE = {
    "raw": DATA_LAKE_ROOT / "raw",
    "processed": DATA_LAKE_ROOT / "processed",
    "curated": DATA_LAKE_ROOT / "curated",
}
PARQUET_ENGINE = "pyarrow"
PARQUET_COMPRESSION = "snappy"

# Backend del Data Lake: "local" (disco del PC) o "s3" (Amazon S3 / MinIO / S3-compatible).
# Con "s3" el pipeline escribe en s3://{S3_BUCKET}/{S3_PREFIX}/{zona}/ en vez del disco.
DATA_LAKE_BACKEND = (os.getenv("DATA_LAKE_BACKEND") or "local").strip().lower()

# ── Amazon S3 (Data Lake en la nube) ───────────────────────
S3_BUCKET = (os.getenv("S3_BUCKET") or "").strip()
S3_PREFIX = (os.getenv("S3_PREFIX") or "").strip().strip("/")  # carpeta raíz dentro del bucket (opcional)
S3_ENDPOINT_URL = (os.getenv("S3_ENDPOINT_URL") or "").strip()  # MinIO u otro S3-compatible; vacío = AWS real
AWS_REGION = (os.getenv("AWS_REGION") or os.getenv("AWS_DEFAULT_REGION") or "us-east-1").strip()
AWS_ACCESS_KEY_ID = (os.getenv("AWS_ACCESS_KEY_ID") or "").strip()
AWS_SECRET_ACCESS_KEY = (os.getenv("AWS_SECRET_ACCESS_KEY") or "").strip()
AWS_SESSION_TOKEN = (os.getenv("AWS_SESSION_TOKEN") or "").strip()

# ── Data Warehouse en la nube (Fase 10) ────────────────────
# "none" (por defecto) = capa APAGADA: el proyecto se comporta igual que siempre.
# "bigquery"           = Google BigQuery (Sandbox gratuita, sin tarjeta de crédito).
# "snowflake"          = Snowflake (Free Trial 30 días con USD 400 de crédito).
DW_BACKEND = (os.getenv("DW_BACKEND") or "none").strip().lower()

# Google BigQuery
BQ_PROJECT = (os.getenv("BQ_PROJECT") or "").strip()          # proyecto GCP (obligatorio con bigquery)
BQ_DATASET = (os.getenv("BQ_DATASET") or "hyperflix").strip()  # dataset dentro del proyecto
BQ_LOCATION = (os.getenv("BQ_LOCATION") or "US").strip()       # ubicación del dataset (US | US-EAST1 | ...)
BQ_MAX_BYTES_BILLED = _entero(os.getenv("BQ_MAX_BYTES_BILLED"), 0)  # tope por consulta (0 = sin tope)
# Ruta al JSON de la service account (si está vacía se usan las ADC de gcloud)
GOOGLE_APPLICATION_CREDENTIALS = (os.getenv("GOOGLE_APPLICATION_CREDENTIALS") or "").strip()

# Snowflake (alternativa a BigQuery; DW_BACKEND=snowflake)
SNOWFLAKE_ACCOUNT = (os.getenv("SNOWFLAKE_ACCOUNT") or "").strip()
SNOWFLAKE_USER = (os.getenv("SNOWFLAKE_USER") or "").strip()
SNOWFLAKE_PASSWORD = (os.getenv("SNOWFLAKE_PASSWORD") or "").strip()
SNOWFLAKE_WAREHOUSE = (os.getenv("SNOWFLAKE_WAREHOUSE") or "COMPUTE_WH").strip()
SNOWFLAKE_DATABASE = (os.getenv("SNOWFLAKE_DATABASE") or "HYPERFLIX_DW").strip()
SNOWFLAKE_SCHEMA = (os.getenv("SNOWFLAKE_SCHEMA") or "PUBLIC").strip()
SNOWFLAKE_ROLE = (os.getenv("SNOWFLAKE_ROLE") or "").strip()

# Mismo esquema estrella que la Fase 9 (data_warehouse.py); la fuente es la
# zona CURATED del Data Lake (fact_reproduccion + dims), renombrada a las
# tablas "oficiales" del DW para poder comparar Mongo vs. nube uno a uno.
TABLAS_DW_NUBE = {
    "fact_reproduccion": "fact_consumo",
    "dim_usuario": "dim_cliente",
    "dim_fecha": "dim_tiempo",
    "dim_pelicula": "dim_pelicula",
}
# Particionamiento y clustering de la tabla de hechos en el DW (rúbrica)
DW_PARTICION = "fecha_id"                                    # columna DATE que BigQuery usa de partición
DW_CLUSTER = ["cliente_id", "pelicula_id", "dispositivo"]    # columnas de clustering
# Cómo se particiona fact_consumo en la nube:
#   "auto"    (por defecto) = sandbox → por INGESTA; con facturación → por fecha de negocio
#   "ingesta" = por fecha de carga (segura en Sandbox: la retención de 60 días corre desde la carga)
#   "fecha"   = por fecha de negocio (DW_PARTICION); requiere proyecto con facturación
# En SANDBOX BigQuery obliga a expirar en <=60 días: si la partición es la fecha de
# negocio, las particiones antiguas desaparecen apenas se cargan.
DW_PARTICION_MODO = (os.getenv("DW_PARTICION_MODO") or "auto").strip().lower()

# ── Dashboard de Monitoreo ────────────────────────────────
CARPETA_DASHBOARD = DATA_LAKE_ROOT.parent / "dashboards"  # Mongo/dashboards
SLA_MS = 500  # umbral "óptimo" de latencia para las consultas OLAP
COSTO_BASE_ATLAS_MES = 57.04  # instancia base MongoDB Atlas (M10, USD/mes)
PRECIO_GB_MENSUAL = 0.07  # almacenamiento estimado (USD/GB/mes)
PRECIO_OPERACIONES_MES = 0.07  # operaciones/mantenimiento estimado (USD/mes)

# ── Estrategia de indexación ───────────────────────────────
# Índices únicos (por colección, campo que debe ser único)
UNIQUE_INDEXES = {
    "generos": "codigo_genero",
    "directores": "codigo_director",
    "planes": "codigo_plan",
    "peliculas": "codigo_pelicula",
    "usuarios": "email",
    "suscripciones": "codigo_suscripcion",
    "pagos": "codigo_pago",
    "resenas": "codigo_resena",
    "reproducciones": "codigo_reproduccion",
}

# Índices compuestos / de consulta (OLTP)
INDEXES_OLTP = {
    "usuarios": [("codigo_usuario", 1)],
    "peliculas": [("genero_codigo", 1), ("director_codigo", 1)],
    "reproducciones": [("fecha_reproduccion", -1), ("usuario_id", 1), ("pelicula_id", 1)],
    "suscripciones": [("usuario_id", 1), ("estado", 1)],
    "pagos": [("suscripcion_id", 1), ("fecha_pago", -1)],
    "resenas": [("pelicula_id", 1), ("puntuacion", -1)],
}

# Índices compuestos (OLAP, usados por el benchmarking)
INDEXES_OLAP = [
    ("idx_fecha", [("anio", 1), ("mes", 1), ("dia", 1)]),
    ("idx_genero_valor", [("pelicula.genero", 1), ("valor_estimado", -1)]),
    ("idx_segmento_ciudad", [("usuario.segmento", 1), ("usuario.ciudad", 1)]),
    ("idx_estado_segmento_ciudad", [("estado", 1), ("usuario.segmento", 1), ("usuario.ciudad", 1)]),
    ("idx_dispositivo_estado", [("dispositivo", 1), ("estado", 1)]),
]