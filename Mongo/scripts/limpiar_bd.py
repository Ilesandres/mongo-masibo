import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pymongo

import config


def limpiar_base_datos():
    if not config.MONGO_URI:
        raise RuntimeError("No se encontró MONGO_URI en el archivo .env configurado.")

    client = pymongo.MongoClient(config.MONGO_URI, serverSelectionTimeoutMS=8000)
    try:
        client.admin.command("ping")
        confirmacion = input(
            f"Escribe HYPERFLIX para eliminar la base '{config.DB_NAME}': "
        ).strip()
        if confirmacion != "HYPERFLIX":
            print("❎ Limpieza cancelada; no se modificó la base de datos.")
            return

        client.drop_database(config.DB_NAME)
        print(f"✅ Base de datos '{config.DB_NAME}' eliminada correctamente.")
    finally:
        client.close()


if __name__ == "__main__":
    limpiar_base_datos()