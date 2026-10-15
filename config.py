import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / "taller-conexion-mongo" / ".env")

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
NUM_USUARIOS = 150_000
NUM_PELICULAS = 7_500
NUM_SUSCRIPCIONES = 200_000
NUM_PAGOS = 750_000
NUM_RESENAS = 300_000
NUM_REPRODUCCIONES = 6_000_000
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