import random
import sys
import time
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # raíz (config)
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # Mongo/ (models)

import pymongo

import config
from models import (
    director,
    genero,
    pago,
    pelicula,
    plan,
    reproduccion,
    resena,
    suscripcion,
    usuario,
)

TOTALES = {
    "generos": config.NUM_GENEROS,
    "directores": config.NUM_DIRECTORES,
    "planes": config.NUM_PLANES,
    "usuarios": config.NUM_USUARIOS,
    "peliculas": config.NUM_PELICULAS,
    "suscripciones": config.NUM_SUSCRIPCIONES,
    "pagos": config.NUM_PAGOS,
    "resenas": config.NUM_RESENAS,
    "reproducciones": config.NUM_REPRODUCCIONES,
}


def conectar_bd():
    client = pymongo.MongoClient(config.MONGO_URI)
    return client[config.DB_NAME]


def insertar_en_lotes(coleccion, datos, nombre_entidad):
    total = len(datos)
    print(f"📦 Insertando {total} {nombre_entidad} en lotes de {config.BATCH_SIZE}...")
    for i in range(0, total, config.BATCH_SIZE):
        lote = datos[i:i + config.BATCH_SIZE]
        try:
            coleccion.insert_many(lote, ordered=False)
            progreso = min(i + config.BATCH_SIZE, total)
            print(f"  ➡️ Progreso: {progreso}/{total} ({(progreso / total) * 100:.1f}%)")
        except pymongo.errors.BulkWriteError as e:
            insertados = e.details.get("nInserted", 0)
            progreso = min(i + config.BATCH_SIZE, total)
            print(f"  ⚠️ Progreso: {progreso}/{total} (Se omitieron {len(lote) - insertados} duplicados)")
    print(f"  ✅ Proceso de {nombre_entidad} finalizado.\n")


def generar_datos():
    if not config.MONGO_URI:
        raise RuntimeError("No se encontró MONGO_URI en el archivo .env configurado.")

    print("🚀 Iniciando generación de datos masivos para HYPERFLIX (MongoDB Atlas)...\n")
    db = conectar_bd()
    inicio_total = time.time()

    print("🎬 Generando catálogos (géneros, directores, planes)...")
    insertar_en_lotes(db.generos, [genero.generar(i) for i in range(config.NUM_GENEROS)], "géneros")
    insertar_en_lotes(db.directores, [director.generar(i) for i in range(config.NUM_DIRECTORES)], "directores")
    insertar_en_lotes(db.planes, [plan.generar(i) for i in range(config.NUM_PLANES)], "planes")

    print("👤 Generando usuarios...")
    planes_bd = list(db.planes.find({}, {"codigo_plan": 1, "nombre": 1}))
    nombres_plan = [p["nombre"] for p in planes_bd]
    insertar_en_lotes(
        db.usuarios,
        [usuario.generar(i, plan=random.choice(nombres_plan)) for i in range(config.NUM_USUARIOS)],
        "usuarios",
    )
    usuarios_ids = [u["_id"] for u in db.usuarios.find({}, {"_id": 1})]
    usuarios_ctx = [
        u for u in db.usuarios.find({}, {"_id": 1, "fecha_registro": 1})
    ]

    print("🎬 Generando películas...")
    generos_codigos = [g["codigo_genero"] for g in db.generos.find({}, {"codigo_genero": 1})]
    directores_codigos = [d["codigo_director"] for d in db.directores.find({}, {"codigo_director": 1})]
    insertar_en_lotes(
        db.peliculas,
        [pelicula.generar(i, generos_codigos, directores_codigos) for i in range(config.NUM_PELICULAS)],
        "películas",
    )
    peliculas_db = list(db.peliculas.find({}, {"_id": 1, "duracion_min": 1}))
    peliculas_ids = [p["_id"] for p in peliculas_db]

    print("🔐 Generando suscripciones...")
    insertar_en_lotes(
        db.suscripciones,
        [suscripcion.generar(i, usuarios_ctx, planes_bd) for i in range(config.NUM_SUSCRIPCIONES)],
        "suscripciones",
    )
    planes_precio = {p["codigo_plan"]: p["precio_mensual"] for p in db.planes.find({}, {"codigo_plan": 1, "precio_mensual": 1})}
    suscripciones_ctx = [
        {
            "_id": s["_id"],
            "codigo_plan": s["codigo_plan"],
            "precio_mensual": planes_precio[s["codigo_plan"]],
            "fecha_inicio": s["fecha_inicio"],
        }
        for s in db.suscripciones.find({}, {"_id": 1, "codigo_plan": 1, "fecha_inicio": 1})
    ]

    print("💳 Generando pagos...")
    insertar_en_lotes(
        db.pagos,
        [pago.generar(i, suscripciones_ctx) for i in range(config.NUM_PAGOS)],
        "pagos",
    )

    print("⭐ Generando reseñas...")
    insertar_en_lotes(
        db.resenas,
        [resena.generar(i, usuarios_ids, peliculas_ids) for i in range(config.NUM_RESENAS)],
        "reseñas",
    )

    print("📺 Generando reproducciones (esto puede tomar varios minutos)...")
    reproducciones = []
    for indice in range(config.NUM_REPRODUCCIONES):
        reproducciones.append(
            reproduccion.generar(indice, usuarios_ids, peliculas_db, config.TARIFA_POR_MINUTO)
        )
        if len(reproducciones) >= config.BATCH_SIZE:
            insertar_en_lotes(db.reproducciones, reproducciones, "reproducciones (lote)")
            reproducciones = []
    if len(reproducciones) > 0:
        insertar_en_lotes(db.reproducciones, reproducciones, "reproducciones (lote final)")

    tiempo_total = time.time() - inicio_total
    print("=" * 50)
    print("🎉 ¡GENERACIÓN DE DATOS COMPLETADA!")
    print(f"⏱️  Tiempo total de ejecución: {tiempo_total:.2f} segundos")
    for coleccion in config.COLECCIONES_OLTP:
        print(f"  - {coleccion}: {db[coleccion].count_documents({})}")
    print("=" * 50)
    db.client.close()


if __name__ == "__main__":
    generar_datos()