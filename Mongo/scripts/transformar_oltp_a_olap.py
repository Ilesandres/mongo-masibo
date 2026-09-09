import sys
import time
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pymongo

import config


def transformar_datos():
    if not config.MONGO_URI:
        raise RuntimeError("No se encontró MONGO_URI en el archivo .env configurado.")

    print("🔄 Iniciando transformación de datos OLTP a OLAP (Modelo Estrella - streaming)...\n")
    client = pymongo.MongoClient(config.MONGO_URI)
    db = client[config.DB_NAME]
    inicio = time.time()

    pipeline = [
        {"$lookup": {
            "from": "usuarios",
            "localField": "usuario_id",
            "foreignField": "_id",
            "as": "info_usuario",
        }},
        {"$unwind": "$info_usuario"},
        {"$lookup": {
            "from": "peliculas",
            "localField": "pelicula_id",
            "foreignField": "_id",
            "as": "info_pelicula",
        }},
        {"$unwind": "$info_pelicula"},
        {"$project": {
            "_id": 1,
            "fecha_reproduccion": 1,
            "anio": {"$year": "$fecha_reproduccion"},
            "mes": {"$month": "$fecha_reproduccion"},
            "dia": {"$dayOfMonth": "$fecha_reproduccion"},
            "usuario": {
                "id": "$info_usuario._id",
                "nombre": "$info_usuario.nombre",
                "ciudad": "$info_usuario.direccion.ciudad",
                "segmento": {
                    "$cond": [
                        {"$gte": ["$valor_estimado", config.SEGMENTO_COMPLETO_MIN]},
                        "Completo",
                        {
                            "$cond": [
                                {"$gte": ["$valor_estimado", config.SEGMENTO_PARCIAL_MIN]},
                                "Parcial",
                                "Corto",
                            ]
                        },
                    ]
                },
            },
            "pelicula": {
                "id": "$info_pelicula._id",
                "titulo": "$info_pelicula.titulo",
                "genero": "$info_pelicula.genero",
                "director": "$info_pelicula.director",
            },
            "minutos_visualizados": 1,
            "valor_estimado": 1,
            "ganancia_estimada": {"$multiply": ["$valor_estimado", config.MARGEN_GANANCIA]},
            "codigo_reproduccion": 1,
            "dispositivo": 1,
            "calidad": 1,
            "estado": 1,
        }},
        {"$merge": {
            "into": config.COLECCION_OLAP,
            "on": "_id",
            "whenMatched": "replace",
            "whenNotMatched": "insert",
        }},
    ]

    print("⚙️ Ejecutando Aggregation Pipeline...")
    list(db.reproducciones.aggregate(pipeline, allowDiskUse=True))
    tiempo_total = time.time() - inicio
    total_analitico = db[config.COLECCION_OLAP].count_documents({})
    print("=" * 60)
    print("🎉 ¡TRANSFORMACIÓN OLTP A OLAP COMPLETADA!")
    print(f"⏱️  Tiempo de procesamiento: {tiempo_total:.2f} segundos")
    print(f"📊 Registros analíticos generados: {total_analitico}")
    print("=" * 60)
    client.close()


if __name__ == "__main__":
    transformar_datos()