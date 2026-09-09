import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / "taller-conexion-mongo" / ".env")

MONGO_URI = os.getenv("MONGO_URI") or os.getenv("mongo_uri")

DB_NAME = "ventas_db"

COLECCIONES_OLTP = ["clientes", "productos", "ventas"]
COLECCION_OLAP = "ventas_analiticas"

NUM_CLIENTES = 5000
NUM_PRODUCTOS = 1000
NUM_VENTAS = 50000
BATCH_SIZE = 1000

MARGEN_GANANCIA = 0.15

INDEXES_OLTP = {
    "clientes": [("email", 1)],
    "productos": [("sku", 1)],
    "ventas": [("fecha_venta", -1), ("cliente_id", 1)],
}

INDEXES_OLAP = [
    ("idx_fecha", [("anio", 1), ("mes", 1), ("dia", 1)]),
    ("idx_categoria_venta", [("producto.categoria", 1), ("total_venta", -1)]),
    ("idx_segmento_ciudad", [("cliente.segmento", 1), ("cliente.ciudad", 1)]),
    ("idx_estado_segmento_ciudad", [("estado", 1), ("cliente.segmento", 1), ("cliente.ciudad", 1)]),
]