import random
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # raíz (config)
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # Mongo/ (models)

import pymongo

import config
from models import director, genero, pago, pelicula, plan, reproduccion, resena, suscripcion, usuario


def _insertar_ejemplo(coleccion, documento, campo_unico):
    coleccion.update_one(
        {campo_unico: documento[campo_unico]},
        {"$setOnInsert": documento},
        upsert=True,
    )


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
    for col, campo in config.UNIQUE_INDEXES.items():
        db[col].create_index([(campo, 1)], unique=True)
    for col, keys in config.INDEXES_OLTP.items():
        db[col].create_index(keys)
    print("  ✅ Índices creados")

    print("\n📝 Insertando datos de prueba (uno por entidad)...")

    genero_ejemplo = genero.generar(0)
    _insertar_ejemplo(db.generos, genero_ejemplo, "codigo_genero")
    print("  ✅ Género insertado")

    director_ejemplo = director.generar(0)
    _insertar_ejemplo(db.directores, director_ejemplo, "codigo_director")
    print("  ✅ Director insertado")

    plan_ejemplo = plan.generar(0)
    _insertar_ejemplo(db.planes, plan_ejemplo, "codigo_plan")
    print("  ✅ Plan insertado")

    usuario_ejemplo = usuario.generar(0, plan="Básico")
    _insertar_ejemplo(db.usuarios, usuario_ejemplo, "codigo_usuario")
    print("  ✅ Usuario insertado")

    pelicula_ejemplo = pelicula.generar(0, ["GEN-001"], ["DIR-001"])
    _insertar_ejemplo(db.peliculas, pelicula_ejemplo, "codigo_pelicula")
    print("  ✅ Película insertada")

    usuario_id = db.usuarios.find_one({"codigo_usuario": "USU00001"})["_id"]
    suscripcion_ejemplo = suscripcion.generar(
        0,
        [{"_id": usuario_id, "fecha_registro": usuario_ejemplo["fecha_registro"]}],
        [{"codigo_plan": "PLA-001"}],
    )
    _insertar_ejemplo(db.suscripciones, suscripcion_ejemplo, "codigo_suscripcion")
    print("  ✅ Suscripción insertada")

    suscripcion_id = db.suscripciones.find_one({"codigo_suscripcion": "SUS000001"})["_id"]
    pago_ejemplo = pago.generar(
        0,
        [{
            "_id": suscripcion_id,
            "precio_mensual": plan_ejemplo["precio_mensual"],
            "fecha_inicio": suscripcion_ejemplo["fecha_inicio"],
        }],
    )
    _insertar_ejemplo(db.pagos, pago_ejemplo, "codigo_pago")
    print("  ✅ Pago insertado")

    pelicula_id = db.peliculas.find_one({"codigo_pelicula": "PEL00001"})["_id"]
    resena_ejemplo = resena.generar(0, [usuario_id], [pelicula_id])
    _insertar_ejemplo(db.resenas, resena_ejemplo, "codigo_resena")
    print("  ✅ Reseña insertada")

    reproduccion_ejemplo = reproduccion.generar(
        0,
        [usuario_id],
        [{"_id": pelicula_id, "duracion_min": pelicula_ejemplo["duracion_min"]}],
        config.TARIFA_POR_MINUTO,
    )
    _insertar_ejemplo(db.reproducciones, reproduccion_ejemplo, "codigo_reproduccion")
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