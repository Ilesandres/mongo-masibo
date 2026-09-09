import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / "taller-conexion-mongo" / ".env")

MONGO_URI = os.getenv("MONGO_URI") or os.getenv("mongo_uri")
DB_NAME = os.getenv("DB_NAME") or os.getenv("db_name") or "hyperflix_BD"

COLECCIONES_OLTP = ["usuarios", "peliculas", "reproducciones"]
COLECCION_OLAP = "reproducciones_analiticas"

NUM_USUARIOS = 5000
NUM_PELICULAS = 1000
NUM_REPRODUCCIONES = 50000
BATCH_SIZE = 1000

TARIFA_POR_MINUTO = 1000
MARGEN_GANANCIA = 0.15
SEGMENTO_COMPLETO_MIN = 90000
SEGMENTO_PARCIAL_MIN = 30000

INDEXES_OLTP = {
    "usuarios": [("email", 1)],
    "peliculas": [("codigo_pelicula", 1)],
    "reproducciones": [("fecha_reproduccion", -1), ("usuario_id", 1)],
}

INDEXES_OLAP = [
    ("idx_fecha", [("anio", 1), ("mes", 1), ("dia", 1)]),
    ("idx_genero_valor", [("pelicula.genero", 1), ("valor_estimado", -1)]),
    ("idx_segmento_ciudad", [("usuario.segmento", 1), ("usuario.ciudad", 1)]),
    ("idx_estado_segmento_ciudad", [("estado", 1), ("usuario.segmento", 1), ("usuario.ciudad", 1)]),
]