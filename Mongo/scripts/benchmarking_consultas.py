import json
import sys
import time
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pymongo

import config


def ejecutar_benchmark():
    if not config.MONGO_URI:
        raise RuntimeError("No se encontró MONGO_URI en el archivo .env configurado.")

    print("🚀 Iniciando Benchmarking de 10 Consultas Analíticas Optimizadas (Hyperflix)...\n")
    client = pymongo.MongoClient(config.MONGO_URI)
    db = client[config.DB_NAME]
    coleccion = db[config.COLECCION_OLAP]

    print("🔧 Fase 1: Aplicando estrategia de indexación...")
    for nombre, keys in config.INDEXES_OLAP:
        coleccion.create_index(keys, name=nombre)
    print("✅ Índices creados exitosamente.\n")

    consultas = [
        {
            "nombre": "1. Reproducciones y minutos totales mensuales",
            "pipeline": [
                {"$group": {"_id": {"anio": "$anio", "mes": "$mes"},
                            "minutos_totales": {"$sum": "$minutos_visualizados"},
                            "reproducciones": {"$sum": 1}}},
                {"$sort": {"_id.anio": 1, "_id.mes": 1}},
            ],
        },
        {
            "nombre": "2. Top 5 Películas por Género",
            "pipeline": [
                {"$group": {"_id": {"genero": "$pelicula.genero", "pelicula": "$pelicula.titulo"},
                            "ingresos": {"$sum": "$valor_estimado"},
                            "minutos": {"$sum": "$minutos_visualizados"}}},
                {"$sort": {"_id.genero": 1, "ingresos": -1}},
                {"$group": {"_id": "$_id.genero",
                            "todos_titulos": {"$push": {"pelicula": "$_id.pelicula", "ingresos": "$ingresos"}}}},
                {"$project": {"genero": "$_id", "top_peliculas": {"$slice": ["$todos_titulos", 5]}, "_id": 0}},
            ],
        },
        {
            "nombre": "3. Rendimiento por Segmento y Ciudad (Top 10)",
            "pipeline": [
                {"$match": {"estado": "Completada"}},
                {"$group": {"_id": {"segmento": "$usuario.segmento", "ciudad": "$usuario.ciudad"},
                            "ingresos": {"$sum": "$valor_estimado"},
                            "ganancia_estimada": {"$sum": "$ganancia_estimada"}}},
                {"$sort": {"ingresos": -1}},
                {"$limit": 10},
                {"$project": {
                    "_id": 0,
                    "segmento": "$_id.segmento",
                    "ciudad": "$_id.ciudad",
                    "ingresos": 1,
                    "ganancia_estimada": 1}},
            ],
        },
        {
            "nombre": "4. Valor Promedio por Dispositivo",
            "pipeline": [
                {"$match": {"estado": "Completada"}},
                {"$group": {"_id": "$dispositivo",
                            "valor_promedio": {"$avg": "$valor_estimado"},
                            "total_reproducciones": {"$sum": 1},
                            "valor_total": {"$sum": "$valor_estimado"}}},
                {"$sort": {"valor_total": -1}},
            ],
        },
        {
            "nombre": "5. Reproducciones por Día de la Semana",
            "pipeline": [
                {"$addFields": {"dia_semana": {"$dayOfWeek": "$fecha_reproduccion"}}},
                {"$group": {"_id": "$dia_semana", "ingresos": {"$sum": "$valor_estimado"},
                            "reproducciones_count": {"$sum": 1}}},
                {"$sort": {"_id": 1}},
            ],
        },
        {
            "nombre": "6. Tasa de Abandono (Interrumpida) por Dispositivo",
            "pipeline": [
                {"$match": {"estado": {"$in": ["Completada", "Interrumpida"]}}},
                {"$group": {"_id": "$dispositivo",
                            "abandonadas": {"$sum": {"$cond": [
                                {"$eq": ["$estado", "Interrumpida"]}, 1, 0]}},
                            "totales": {"$sum": 1}}},
                {"$project": {"_id": 0,
                              "dispositivo": "$_id",
                              "abandonadas": 1,
                              "totales": 1,
                              "tasa_abandono_pct": {"$round": [
                                  {"$multiply": [{"$divide": ["$abandonadas", "$totales"]}, 100]}, 2]}}},
                {"$sort": {"tasa_abandono_pct": -1}},
            ],
        },
        {
            "nombre": "7. Top 10 Clientes VIP por Gasto Acumulado",
            "pipeline": [
                {"$match": {"usuario.segmento": "Completo"}},
                {"$group": {"_id": "$usuario.id",
                            "nombre": {"$first": "$usuario.nombre"},
                            "compras": {"$sum": 1},
                            "gasto_total": {"$sum": "$valor_estimado"}}},
                {"$sort": {"gasto_total": -1}},
                {"$limit": 10},
                {"$project": {"_id": 0, "cliente_id": {"$toString": "$_id"},
                              "nombre": 1, "compras": 1, "gasto_total": 1}},
            ],
        },
        {
            "nombre": "8. Reproducciones Trimestrales (Análisis Estacional Q1-Q4)",
            "pipeline": [
                {"$group": {"_id": {"anio": "$anio",
                                    "trimestre": {"$ceil": {"$divide": ["$mes", 3]}}},
                            "ingresos": {"$sum": "$valor_estimado"},
                            "reproducciones": {"$sum": 1}}},
                {"$sort": {"_id.anio": 1, "_id.trimestre": 1}},
                {"$project": {"_id": 0,
                              "anio": "$_id.anio",
                              "trimestre": {"$concat": ["Q", {"$toString": "$_id.trimestre"}]},
                              "ingresos": 1, "reproducciones": 1}},
            ],
        },
        {
            "nombre": "9. Ticket Promedio por Ciudad y Segmento (Top 15)",
            "pipeline": [
                {"$match": {"estado": "Completada"}},
                {"$group": {"_id": {"ciudad": "$usuario.ciudad", "segmento": "$usuario.segmento"},
                            "ticket_promedio": {"$avg": "$valor_estimado"},
                            "transacciones": {"$sum": 1}}},
                {"$sort": {"ticket_promedio": -1, "_id.segmento": 1}},
                {"$limit": 15},
                {"$project": {"_id": 0, "ciudad": "$_id.ciudad", "segmento": "$_id.segmento",
                              "ticket_promedio": {"$round": ["$ticket_promedio", 2]},
                              "transacciones": 1}},
            ],
        },
        {
            "nombre": "10. Top 10 Películas con Mayor Rotación (Reproducciones)",
            "pipeline": [
                {"$match": {"estado": "Completada"}},
                {"$group": {"_id": "$pelicula.id",
                            "titulo": {"$first": "$pelicula.titulo"},
                            "reproducciones": {"$sum": 1},
                            "ingresos_generados": {"$sum": "$valor_estimado"}}},
                {"$sort": {"reproducciones": -1}},
                {"$limit": 10},
                {"$project": {"_id": 0, "pelicula": "$titulo",
                              "reproducciones": 1, "ingresos_generados": 1}},
            ],
        },
    ]

    print("⚙️ Fase 2: Ejecutando consultas...\n")
    print("-" * 70)
    tiempos_totales = []
    for consulta in consultas:
        print(f"▶️ {consulta['nombre']}")
        inicio = time.perf_counter()
        resultados = list(coleccion.aggregate(consulta["pipeline"], allowDiskUse=True))
        fin = time.perf_counter()
        tiempo_ms = (fin - inicio) * 1000
        tiempos_totales.append(tiempo_ms)
        print(f"   ⏱️ Latencia: {tiempo_ms:.2f} ms | 📊 Filas: {len(resultados)}")
        if len(resultados) > 0:
            resultado_limpio = json.loads(json.dumps(resultados[0], default=str))
            print(f"   💡 Muestra: {resultado_limpio}")
        print("-" * 70)

    promedio_latencia = sum(tiempos_totales) / len(tiempos_totales)
    print("\n" + "=" * 70)
    print("📊 RESUMEN DE BENCHMARKING DE RENDIMIENTO (10 CONSULTAS)")
    print("=" * 70)
    print(f"✅ Consultas ejecutadas: {len(consultas)}")
    print(f"⏱️  Latencia promedio: {promedio_latencia:.2f} ms")
    print(f"🚀 Latencia máxima: {max(tiempos_totales):.2f} ms")
    print(f"📊 Registros analíticos procesados: {coleccion.count_documents({})}")
    sla_ms = 500
    if promedio_latencia <= sla_ms:
        print("=" * 70)
        print(f"✅ CONCLUSIÓN: RENDIMIENTO ÓPTIMO. Índices compuestos + allowDiskUse"
              f" garantizan latencia < {sla_ms} ms (SLA OLAP).")
    else:
        print("=" * 70)
        print(f"⚠️  Latencia promedio supera los {sla_ms} ms.")
        print("    Lección: en OLAP, la latencia no solo depende del índice, sino del")
        print("    VOLUMEN de filas devuelto al cliente (usa $limit / filas agregadas).")
    print("=" * 70)
    client.close()


if __name__ == "__main__":
    ejecutar_benchmark()