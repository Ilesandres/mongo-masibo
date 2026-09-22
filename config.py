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
NUM_DIRECTORES = 300
NUM_PLANES = 3
NUM_USUARIOS = 10_000
NUM_PELICULAS = 2_000
NUM_SUSCRIPCIONES = 8_000
NUM_PAGOS = 25_000
NUM_RESENAS = 20_000
NUM_REPRODUCCIONES = 100_000
BATCH_SIZE = 1_000

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