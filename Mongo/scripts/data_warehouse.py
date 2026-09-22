import sys
import time
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pymongo

import config

PIPELINE_DIM_TIEMPO = [
    {"$group": {
        "_id": {"anio": "$anio", "mes": "$mes", "dia": "$dia"},
    }},
    {"$project": {
        "_id": {
            "$dateFromParts": {"year": "$_id.anio", "month": "$_id.mes", "day": "$_id.dia"}
        },
        "anio": "$_id.anio",
        "mes": "$_id.mes",
        "dia": "$_id.dia",
        "trimestre": {"$ceil": {"$divide": ["$_id.mes", 3]}},
        "dia_semana": {
            "$dayOfWeek": {
                "$dateFromParts": {"year": "$_id.anio", "month": "$_id.mes", "day": "$_id.dia"}
            }
        },
    }},
    {"$addFields": {
        "fin_semana": {"$cond": [{"$in": ["$dia_semana", [1, 7]]}, "Sí", "No"]},
    }},
    {"$sort": {"anio": 1, "mes": 1, "dia": 1}},
    {"$merge": {
        "into": config.COLECCIONES_DW[0],
        "whenMatched": "replace",
        "whenNotMatched": "insert",
    }},
]

PIPELINE_DIM_CLIENTE = [
    {"$group": {
        "_id": "$usuario.id",
        "nombre": {"$first": "$usuario.nombre"},
        "ciudad": {"$first": "$usuario.ciudad"},
        "segmento": {"$first": "$usuario.segmento"},
        "reproducciones": {"$sum": 1},
        "minutos_totales": {"$sum": "$minutos_visualizados"},
        "gasto_total": {"$sum": "$valor_estimado"},
        "valor_promedio": {"$avg": "$valor_estimado"},
    }},
    {"$project": {
        "_id": 1,
        "nombre": 1,
        "ciudad": 1,
        "segmento": 1,
        "reproducciones": 1,
        "minutos_totales": 1,
        "gasto_total": {"$round": ["$gasto_total", 0]},
        "valor_promedio": {"$round": ["$valor_promedio", 0]},
    }},
    {"$sort": {"gasto_total": -1}},
    {"$merge": {
        "into": config.COLECCIONES_DW[1],
        "whenMatched": "replace",
        "whenNotMatched": "insert",
    }},
]

PIPELINE_DIM_PELICULA = [
    {"$group": {
        "_id": "$pelicula.id",
        "titulo": {"$first": "$pelicula.titulo"},
        "genero": {"$first": "$pelicula.genero"},
        "director": {"$first": "$pelicula.director"},
        "reproducciones": {"$sum": 1},
        "minutos_totales": {"$sum": "$minutos_visualizados"},
        "ingresos_totales": {"$sum": "$valor_estimado"},
    }},
    {"$project": {
        "_id": 1,
        "titulo": 1,
        "genero": 1,
        "director": 1,
        "reproducciones": 1,
        "minutos_totales": 1,
        "ingresos_totales": {"$round": ["$ingresos_totales", 0]},
    }},
    {"$sort": {"ingresos_totales": -1}},
    {"$merge": {
        "into": config.COLECCIONES_DW[2],
        "whenMatched": "replace",
        "whenNotMatched": "insert",
    }},
]

PIPELINE_FACT_CONSUMO = [
    {"$project": {
        "_id": "$codigo_reproduccion",
        "fecha_id": {
            "$dateFromParts": {"year": "$anio", "month": "$mes", "day": "$dia"}
        },
        "cliente_id": "$usuario.id",
        "pelicula_id": "$pelicula.id",
        "minutos_visualizados": 1,
        "valor_estimado": 1,
        "ganancia_estimada": 1,
        "estado": 1,
        "dispositivo": 1,
        "calidad": 1,
    }},
    {"$merge": {
        "into": config.COLECCIONES_DW[3],
        "on": "_id",
        "whenMatched": "replace",
        "whenNotMatched": "insert",
    }},
]


def construir_data_warehouse():
    if not config.MONGO_URI:
        raise RuntimeError("No se encontró MONGO_URI en el archivo .env configurado.")

    print("🔄 Construyendo Data Warehouse (Modelo Estrella) en MongoDB...\n")
    client = pymongo.MongoClient(config.MONGO_URI)
    db = client[config.DB_NAME]
    fuente = config.COLECCION_OLAP

    total_fuente = db[fuente].count_documents({})
    if total_fuente == 0:
        print(f"⚠️  La colección fuente '{fuente}' está vacía.")
        print("→ Ejecuta primero la Fase 4 (transformar_oltp_a_olap.py).")
        client.close()
        return

    inicio = time.time()

    print("📅 Dim Tiempo: agrupando por fecha (año, mes, día) y calculando trimestre / fin de semana...")
    db[config.COLECCIONES_DW[0]].drop()
    db[fuente].aggregate(PIPELINE_DIM_TIEMPO, allowDiskUse=True)
    print(f"   ✓ dim_tiempo  → {db[config.COLECCIONES_DW[0]].count_documents({})} registros")

    print("👤 Dim Cliente: perfil único por usuario ($first) con totales ($sum) y promedio ($avg)...")
    db[config.COLECCIONES_DW[1]].drop()
    db[fuente].aggregate(PIPELINE_DIM_CLIENTE, allowDiskUse=True)
    print(f"   ✓ dim_cliente → {db[config.COLECCIONES_DW[1]].count_documents({})} registros")

    print("🎬 Dim Película: catálogo único por película con minutos reproducidos e ingresos...")
    db[config.COLECCIONES_DW[2]].drop()
    db[fuente].aggregate(PIPELINE_DIM_PELICULA, allowDiskUse=True)
    print(f"   ✓ dim_pelicula → {db[config.COLECCIONES_DW[2]].count_documents({})} registros")

    print("📊 Fact Consumo: medidas puras con solo las claves (IDs) en lugar de datos duplicados...")
    db[config.COLECCIONES_DW[3]].drop()
    db[fuente].aggregate(PIPELINE_FACT_CONSUMO, allowDiskUse=True)
    print(f"   ✓ fact_consumo → {db[config.COLECCIONES_DW[3]].count_documents({})} registros")

    tiempo_total = time.time() - inicio
    print("=" * 60)
    print("🎉 ¡DATA WAREHOUSE CONFIGURADO!")
    print(f"⏱️  Tiempo de procesamiento: {tiempo_total:.2f} segundos")
    print("-" * 60)
    for coleccion in config.COLECCIONES_DW:
        print(f"📊 {coleccion:<14} → {db[coleccion].count_documents({}):>10} registros")
    print("=" * 60)
    client.close()


if __name__ == "__main__":
    construir_data_warehouse()