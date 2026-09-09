import random
import sys
import time
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pymongo
from faker import Faker

import config

fake = Faker('es_CO')


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
            insertados = e.details.get('nInserted', 0)
            progreso = min(i + config.BATCH_SIZE, total)
            print(f"  ⚠️ Progreso: {progreso}/{total} (Se omitieron {len(lote) - insertados} duplicados)")
    print(f"  ✅ Proceso de {nombre_entidad} finalizado.\n")


def generar_datos():
    if not config.MONGO_URI:
        raise RuntimeError("No se encontró MONGO_URI en el archivo .env configurado.")

    print("🚀 Iniciando generación de datos masivos para HYPERFLIX (MongoDB Atlas)...\n")
    db = conectar_bd()
    inicio_total = time.time()

    print("👤 Generando usuarios...")
    planes = ["Básico", "Estándar", "Estándar", "Premium", "Premium"]
    usuarios = []
    for indice in range(config.NUM_USUARIOS):
        usuarios.append({
            "codigo_usuario": f"USU{indice + 1:05d}",
            "nombre": fake.name(),
            "email": f"usuario{indice + 1}@hyperflix.local",
            "telefono": fake.phone_number(),
            "direccion": {
                "calle": fake.street_address(),
                "ciudad": fake.city(),
                "pais": "Colombia",
            },
            "fecha_registro": fake.date_time_between(start_date='-2y', end_date='now'),
            "activo": random.choice([True, True, True, False]),
            "plan": random.choice(planes),
        })
    insertar_en_lotes(db.usuarios, usuarios, "usuarios")
    usuarios_ids = [u["_id"] for u in db.usuarios.find({}, {"_id": 1})]

    print("🎬 Generando películas...")
    generos = ["Acción", "Comedia", "Drama", "Ciencia Ficción", "Terror", "Documental", "Romance"]
    peliculas = []
    for indice in range(config.NUM_PELICULAS):
        anio = random.randint(1990, 2026)
        peliculas.append({
            "codigo_pelicula": f"PEL{indice + 1:05d}",
            "titulo": f"{fake.word().capitalize()} {fake.word().capitalize()}",
            "genero": random.choice(generos),
            "anio": anio,
            "duracion_min": random.randint(75, 180),
            "director": fake.name(),
            "fecha_estreno": fake.date_time_between(
                start_date=f"-{2026 - anio}y", end_date='now'),
        })
    insertar_en_lotes(db.peliculas, peliculas, "películas")
    peliculas_db = list(db.peliculas.find({}, {"_id": 1, "titulo": 1, "duracion_min": 1}))

    print("📺 Generando reproducciones (esto puede tomar unos minutos)...")
    dispositivos = ["Smart TV", "Smartphone", "Tablet", "PC", "Consola"]
    calidades = ["SD", "HD", "HD", "4K"]
    estados = ["Completada", "Completada", "Completada", "Interrumpida", "Pendiente"]
    reproducciones = []
    for indice in range(config.NUM_REPRODUCCIONES):
        pelicula = random.choice(peliculas_db)
        duracion = pelicula["duracion_min"]
        estado = random.choice(estados)
        if estado == "Completada":
            minutos = duracion
        else:
            minutos = random.randint(5, max(6, duracion - 1))
        reproducciones.append({
            "codigo_reproduccion": f"REP-2026-{indice + 1:06d}",
            "usuario_id": random.choice(usuarios_ids),
            "pelicula_id": pelicula["_id"],
            "fecha_reproduccion": fake.date_time_between(start_date='-1y', end_date='now'),
            "dispositivo": random.choice(dispositivos),
            "calidad": random.choice(calidades),
            "estado": estado,
            "minutos_visualizados": minutos,
            "progreso_pct": round(min(minutos / duracion * 100, 100), 1),
            "valor_estimado": round(minutos * config.TARIFA_POR_MINUTO, 2),
        })
        if len(reproducciones) >= config.BATCH_SIZE:
            insertar_en_lotes(db.reproducciones, reproducciones, "reproducciones (lote)")
            reproducciones = []
    if len(reproducciones) > 0:
        insertar_en_lotes(db.reproducciones, reproducciones, "reproducciones (lote final)")

    tiempo_total = time.time() - inicio_total
    print("=" * 50)
    print("🎉 ¡GENERACIÓN DE DATOS COMPLETADA!")
    print(f"⏱️  Tiempo total de ejecución: {tiempo_total:.2f} segundos")
    print(f"👤 Usuarios en BD: {db.usuarios.count_documents({})}")
    print(f"🎬 Películas en BD: {db.peliculas.count_documents({})}")
    print(f"📺 Reproducciones en BD: {db.reproducciones.count_documents({})}")
    print("=" * 50)
    db.client.close()


if __name__ == "__main__":
    generar_datos()