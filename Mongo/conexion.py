import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pymongo
from pymongo.errors import ConfigurationError, ConnectionFailure, OperationFailure

import config


def conectar_mongodb():
    try:
        print("🔄 Intentando conectar a MongoDB Atlas...")
        client = pymongo.MongoClient(config.MONGO_URI, serverSelectionTimeoutMS=5000)
        client.admin.command("ping")
        print("✅ ¡Conexión exitosa a MongoDB Atlas!")
        db = client[config.DB_NAME]
        return client, db
    except ConnectionFailure:
        print("❌ Error: No se pudo contactar al servidor.")
    except ConfigurationError as e:
        print(f"❌ Error de configuración: {e}")
    except OperationFailure as e:
        print(f"❌ Error de autenticación: {e}")
    return None, None


if __name__ == "__main__":
    client, db = conectar_mongodb()
    if client:
        client.close()
        print("🔒 Conexión cerrada.")