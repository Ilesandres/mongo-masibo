import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from datetime import datetime

import pymongo

import config


def crear_estructura_hyperflix():
    if not config.MONGO_URI:
        raise RuntimeError("No se encontró MONGO_URI en el archivo .env configurado.")

    client = pymongo.MongoClient(config.MONGO_URI)
    db = client[config.DB_NAME]
    print(f"🏗️ Creando estructura de HYPERFLIX ({config.DB_NAME})...\n")

    print("📦 Creando colecciones transaccionales (OLTP)...")
    for col in config.COLECCIONES_OLTP:
        if col not in db.list_collection_names():
            db.create_collection(col)
        print(f"  ✅ Colección '{col}' creada")

    print("\n🔍 Creando índices...")
    db.usuarios.create_index([("email", 1)], unique=True)
    db.peliculas.create_index([("codigo_pelicula", 1)], unique=True)
    db.reproducciones.create_index([("codigo_reproduccion", 1)], unique=True)
    db.reproducciones.create_index([("fecha_reproduccion", -1)])
    db.reproducciones.create_index([("usuario_id", 1)])
    print("  ✅ Índices creados")

    print("\n📝 Insertando datos de prueba...")
    usuario_ejemplo = {
        "codigo_usuario": "USU001",
        "nombre": "Ana García",
        "email": "ana.garcia@email.com",
        "telefono": "3009876543",
        "direccion": {
            "calle": "Carrera 7 #12-34",
            "ciudad": "Bogotá",
            "pais": "Colombia",
        },
        "fecha_registro": datetime.now(),
        "activo": True,
        "plan": "Premium",
    }
    db.usuarios.update_one(
        {"codigo_usuario": usuario_ejemplo["codigo_usuario"]},
        {"$setOnInsert": usuario_ejemplo},
        upsert=True,
    )
    print("  ✅ Usuario insertado")

    pelicula_ejemplo = {
        "codigo_pelicula": "PEL001",
        "titulo": "Interstelar Virtual",
        "genero": "Ciencia Ficción",
        "anio": 2025,
        "duracion_min": 148,
        "director": "Director Ejemplo",
        "fecha_estreno": datetime(2025, 6, 15),
    }
    db.peliculas.update_one(
        {"codigo_pelicula": pelicula_ejemplo["codigo_pelicula"]},
        {"$setOnInsert": pelicula_ejemplo},
        upsert=True,
    )
    print("  ✅ Película insertada")

    reproduccion_ejemplo = {
        "codigo_reproduccion": "REP-2026-0001",
        "usuario_id": db.usuarios.find_one({"codigo_usuario": "USU001"})["_id"],
        "pelicula_id": db.peliculas.find_one({"codigo_pelicula": "PEL001"})["_id"],
        "fecha_reproduccion": datetime.now(),
        "dispositivo": "Smart TV",
        "calidad": "4K",
        "estado": "Completada",
        "minutos_visualizados": 148,
        "progreso_pct": 100.0,
        "valor_estimado": round(148 * config.TARIFA_POR_MINUTO, 2),
    }
    db.reproducciones.update_one(
        {"codigo_reproduccion": reproduccion_ejemplo["codigo_reproduccion"]},
        {"$setOnInsert": reproduccion_ejemplo},
        upsert=True,
    )
    print("  ✅ Reproducción insertada")

    print("\n📊 Creando colección analítica (OLAP)...")
    if config.COLECCION_OLAP not in db.list_collection_names():
        db.create_collection(config.COLECCION_OLAP)
    print(f"  ✅ Colección '{config.COLECCION_OLAP}' creada")

    print("\n✅ Estructura de HYPERFLIX creada exitosamente en Atlas!")
    print("🔍 Abre MongoDB Compass para ver las colecciones creadas.")
    client.close()


if __name__ == "__main__":
    crear_estructura_hyperflix()