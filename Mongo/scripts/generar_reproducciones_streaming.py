"""Generador de reproducciones en streaming (simula la Aplicación Web) — Terminal 2.

Inserta/actualiza/elimina documentos en la colección `reproducciones` en tiempo
real para que la Terminal 1 (`streaming.py`) los detecte vía Change Streams.

Equivale en producción a la ingesta de eventos hacia Kafka.

Cómo usarlo:
    Terminal 1 (abierta primero):  python Mongo/scripts/streaming.py
    Terminal 2 (esta):             python Mongo/scripts/generar_reproducciones_streaming.py
"""

import random
import sys
import time
from datetime import datetime
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # raíz (config)

import pymongo

import config

DISPOSITIVOS = ["Smart TV", "Smartphone", "Tablet", "PC", "Consola"]
CALIDADES = ["SD", "HD", "HD", "4K"]
ESTADOS_FINALES = ["Completada", "Completada", "Completada", "Interrumpida"]


def generar_reproducciones(numero_eventos=25):
    if not config.MONGO_URI:
        raise RuntimeError("No se encontró MONGO_URI en el archivo .env configurado.")

    client = pymongo.MongoClient(config.MONGO_URI)
    db = client[config.DB_NAME]

    usuarios_ids = [u["_id"] for u in db.usuarios.find({}, {"_id": 1}).limit(5_000)]
    peliculas_db = list(db.peliculas.find({}, {"_id": 1, "titulo": 1, "duracion_min": 1}).limit(1_000))

    if not usuarios_ids or not peliculas_db:
        print("⚠️ La base debe tener usuarios y películas. Ejecuta primero crear_estructura.py y generar_datos_masivos.py.")
        client.close()
        return

    codigo_base = datetime.now().strftime("%Y%m%d%H%M%S")
    print(f"🎬 Generando {numero_eventos} reproducciones en streaming hacia '{config.DB_NAME}.reproducciones'...\n")

    for indice in range(numero_eventos):
        usuario_id = random.choice(usuarios_ids)
        pelicula = random.choice(peliculas_db)
        codigo = f"STR-{codigo_base}-{indice + 1:03d}"

        # 1) INSERT — el usuario inicia la reproducción (estado Pendiente)
        documento = {
            "codigo_reproduccion": codigo,
            "usuario_id": usuario_id,
            "pelicula_id": pelicula["_id"],
            "fecha_reproduccion": datetime.now(),
            "dispositivo": random.choice(DISPOSITIVOS),
            "calidad": random.choice(CALIDADES),
            "estado": "Pendiente",
            "minutos_visualizados": 0,
            "progreso_pct": 0.0,
            "valor_estimado": 0,
        }
        db.reproducciones.insert_one(documento)
        print(f"📤 [INSERT] {codigo} | {pelicula['titulo']} | Pendiente")
        time.sleep(0.8)

        # 2) Con poca probabilidad: DELETE (auditoría), en caso contrario: UPDATE
        if random.random() < 0.12:
            db.reproducciones.delete_one({"codigo_reproduccion": codigo})
            print(f"🗑️ [DELETE] {codigo} | documento eliminado (auditoría)")
        else:
            estado_final = random.choice(ESTADOS_FINALES)
            if estado_final == "Completada":
                minutos = pelicula["duracion_min"]
            else:
                minutos = random.randint(5, max(6, pelicula["duracion_min"] - 1))
            valor = round(minutos * config.TARIFA_POR_MINUTO, 2)
            db.reproducciones.update_one(
                {"codigo_reproduccion": codigo},
                {"$set": {
                    "estado": estado_final,
                    "minutos_visualizados": minutos,
                    "progreso_pct": round(min(minutos / pelicula["duracion_min"] * 100, 100), 1),
                    "valor_estimado": valor,
                }},
            )
            print(f"🔄 [UPDATE] {codigo} | {pelicula['titulo']} | -> {estado_final} | {minutos} min | 💰 ${valor:,.0f}")

        time.sleep(1.2)

    print("\n✅ Generación de streaming finalizada.")
    client.close()


if __name__ == "__main__":
    numero = int(sys.argv[1]) if len(sys.argv) > 1 else 25
    generar_reproducciones(numero)