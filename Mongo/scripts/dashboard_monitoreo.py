import sys
import time
from datetime import datetime
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import matplotlib

matplotlib.use("Agg")
import matplotlib.ticker as mticker
import matplotlib.pyplot as plt
import pymongo

import config

COLECCIONES_DASHBOARD = config.COLECCIONES_OLTP + [config.COLECCION_OLAP] + config.COLECCIONES_DW

CONSULTAS_DASHBOARD = [
    {
        "nombre": "Tendencia Mensual de Consumo",
        "pipeline": [
            {"$group": {"_id": {"anio": "$anio", "mes": "$mes"},
                        "minutos": {"$sum": "$minutos_visualizados"},
                        "ingresos": {"$sum": "$valor_estimado"}}},
            {"$sort": {"_id.anio": 1, "_id.mes": 1}},
        ],
    },
    {
        "nombre": "Agrupación por Dispositivo",
        "pipeline": [
            {"$group": {"_id": "$dispositivo",
                        "reproducciones": {"$sum": 1},
                        "ingresos": {"$sum": "$valor_estimado"}}},
            {"$sort": {"_id": 1}},
        ],
    },
    {
        "nombre": "Análisis Temporal Trimestral",
        "pipeline": [
            {"$group": {"_id": {"anio": "$anio",
                                "trimestre": {"$ceil": {"$divide": ["$mes", 3]}}},
                        "ingresos": {"$sum": "$valor_estimado"}}},
            {"$sort": {"_id.anio": 1, "_id.trimestre": 1}},
        ],
    },
]


def estadisticas_por_coleccion(db):
    """Cuenta documentos y tamaño real (dataSize) de cada colección."""
    info = []
    for nombre in COLECCIONES_DASHBOARD:
        try:
            docs = db[nombre].count_documents({})
            coll_stats = db.command("collStats", nombre)
            tamano = coll_stats.get("size", 0)
        except Exception:
            docs, tamano = 0, 0
        info.append({"coleccion": nombre, "docs": docs, "bytes": tamano})
    return info


def ejecutar_mini_benchmark(db):
    """Mide la latencia de 3 consultas representativas sobre la vista OLAP."""
    resultados = []
    for consulta in CONSULTAS_DASHBOARD:
        inicio = time.perf_counter()
        filas = len(list(db[config.COLECCION_OLAP].aggregate(
            consulta["pipeline"], allowDiskUse=True)))
        latencia_ms = (time.perf_counter() - inicio) * 1000
        resultados.append({"nombre": consulta["nombre"], "latencia_ms": latencia_ms, "filas": filas})
    return resultados


def tendencia_mensual(db):
    serie = list(db[config.COLECCION_OLAP].aggregate([
        {"$group": {"_id": {"anio": "$anio", "mes": "$mes"},
                    "ingresos": {"$sum": "$valor_estimado"}}},
        {"$sort": {"_id.anio": 1, "_id.mes": 1}},
    ], allowDiskUse=True))
    etiquetas = [f"{d['_id']['anio']}-{d['_id']['mes']:02d}" for d in serie]
    ingresos = [d["ingresos"] for d in serie]
    return etiquetas, ingresos


def construir_dashboard(info, resultados, consultas, total_docs, almacenamiento_gb,
                        costo_mensual, partes_costo, meses_con_datos, serie_mensual):
    fig, ejes = plt.subplots(2, 3, figsize=(18, 11))
    fig.suptitle("DASHBOARD DE MONITOREO - Arquitectura de Datos (Hyperflix)",
                 fontsize=18, fontweight="bold")

    # 1. Documentos por colección
    ax = ejes[0, 0]
    nombres = [i["coleccion"] for i in info]
    cantidades = [i["docs"] for i in info]
    colores = ["#d62728" if "analiticas" in n else "#e377c2" if n in config.COLECCIONES_DW
               else "#1f77b4" for n in nombres]
    ax.bar(nombres, cantidades, color=colores)
    ax.set_title("1. Documentos por Colección")
    ax.set_ylabel("Documentos")
    ax.tick_params(axis="x", rotation=60, labelsize=8)
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda v, p: f"{v:,.0f}"))

    # 2. Rendimiento de consultas
    ax = ejes[0, 1]
    nombres_q = [r["nombre"] for r in resultados]
    latencias = [r["latencia_ms"] for r in resultados]
    ax.bar(nombres_q, latencias, color="#2ca02c")
    ax.axhline(config.SLA_MS, color="lime", linestyle="--", linewidth=2)
    ax.text(len(nombres_q) - 0.4, config.SLA_MS + 12, f"Óptimo (<{config.SLA_MS}ms)",
            color="green", fontsize=9)
    ax.set_title("2. Rendimiento de Consultas (OLAP)")
    ax.set_ylabel("Latencia (ms)")
    ax.tick_params(axis="x", rotation=15, labelsize=8)
    for i, lat in enumerate(latencias):
        ax.text(i, lat + 6, f"{lat:.0f}", ha="center", fontsize=9)

    # 3. Estimación de costos mensuales
    ax = ejes[0, 2]
    etiquetas_costo = [f"{k}\n${v:,.2f}" for k, v in partes_costo.items()]
    valores_costo = list(partes_costo.values())
    ax.pie(valores_costo, labels=etiquetas_costo, autopct="%1.1f%%",
           colors=["#1f77b4", "#ff7f0e", "#2ca02c"], startangle=90, counterclock=False)
    ax.text(0, 0, f"Total\n${costo_mensual:,.2f}", ha="center", va="center",
            fontsize=11, fontweight="bold")
    ax.set_title("3. Estimación de Costos Mensuales")

    # 4. Tendencia de consumo mensual
    ax = ejes[1, 0]
    etiquetas_t, ingresos = serie_mensual
    ax.plot(etiquetas_t, ingresos, marker="o", color="#9467bd")
    ax.set_title("4. Tendencia de Consumo Mensual (ingresos estimados)")
    ax.set_ylabel("Valor estimado (COP)")
    ax.tick_params(axis="x", rotation=45, labelsize=7)
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda v, p: f"{v/1_000_000:,.1f}M"))

    # 5. Métricas de almacenamiento normalizadas (0-100%)
    ax = ejes[1, 1]
    metricas = [100, (almacenamiento_gb / total_docs) * 100, (meses_con_datos / total_docs) * 100]
    nombres_m = ["Total\nDocumentos", "GB\nEstimados", "Meses\ncon Datos"]
    ax.bar(nombres_m, metricas, color=["#1f77b4", "#ff7f0e", "#2ca02c"])
    ax.set_title("5. Métricas de Almacenamiento (normalizado)")
    ax.set_ylabel("Escala 0-100%")
    ax.set_ylim(0, 105)

    # 6. Resumen ejecutivo
    ax = ejes[1, 2]
    ax.axis("off")
    estado = "OPERATIVO"
    resumen = (
        "RESUMEN EJECUTIVO DEL SISTEMA\n"
        "------------------------------\n"
        f"Total Documentos   : {total_docs:,}\n"
        f"Almacenamiento     : {almacenamiento_gb:.2f} GB\n"
        f"Latencia Promedio  : {consultas['promedio_ms']:.2f} ms\n"
        f"Costo Estimado     : ${costo_mensual:,.2f}\n"
        f"Estado del Sistema : {estado}\n"
        f"Colecciones Activas: {len(info)}\n"
        f"Meses con Datos    : {meses_con_datos}"
    )
    ax.text(0.5, 0.5, resumen, transform=ax.transAxes, ha="center", va="center",
            fontfamily="monospace", fontsize=13,
            bbox=dict(boxstyle="round", facecolor="black", edgecolor="#2ca02c"))

    fig.tight_layout(rect=(0, 0, 1, 0.95))
    return fig


def generar_dashboard():
    if not config.MONGO_URI:
        raise RuntimeError("No se encontró MONGO_URI en el archivo .env configurado.")

    client = pymongo.MongoClient(config.MONGO_URI)
    db = client[config.DB_NAME]

    if db[config.COLECCION_OLAP].count_documents({}) == 0:
        print("⚠️  La colección fuente 'reproducciones_analiticas' está vacía.")
        print("→ Ejecuta primero la Fase 4 (transformar_oltp_a_olap.py).")
        client.close()
        return

    inicio = time.perf_counter()
    print("📊 Generando Dashboard de Monitoreo (Hyperflix)...")

    print("🔎 1/4  Analizando colecciones...")
    info = estadisticas_por_coleccion(db)
    total_docs = sum(i["docs"] for i in info)
    almacenamiento_gb = sum(i["bytes"] for i in info) / (1024 ** 3)

    print("⚡ 2/4  Ejecutando consultas de rendimiento...")
    resultados = ejecutar_mini_benchmark(db)
    promedio_ms = sum(r["latencia_ms"] for r in resultados) / len(resultados)

    print("💰 3/4  Calculando costos y tendencias...")
    partes_costo = {
        "Base (M10)": config.COSTO_BASE_ATLAS_MES,
        "Almacenamiento": almacenamiento_gb * config.PRECIO_GB_MENSUAL,
        "Operaciones": config.PRECIO_OPERACIONES_MES,
    }
    costo_mensual = sum(partes_costo.values())

    meses_con_datos = db[config.COLECCION_OLAP].aggregate([
        {"$group": {"_id": {"anio": "$anio", "mes": "$mes"}}},
        {"$count": "total"},
    ], allowDiskUse=True)
    meses_con_datos = next(iter(list(meses_con_datos)), {}).get("total", 0)

    consultas = {"promedio_ms": promedio_ms}
    serie_mensual = tendencia_mensual(db)

    print("🎨 4/4  Dibujando los 6 paneles...")
    fig = construir_dashboard(info, resultados, consultas, total_docs,
                              almacenamiento_gb, costo_mensual, partes_costo,
                              meses_con_datos, serie_mensual)

    config.CARPETA_DASHBOARD.mkdir(parents=True, exist_ok=True)
    archivo = config.CARPETA_DASHBOARD / f"dashboard_monitoreo_{datetime.now():%Y%m%d_%H%M%S}.png"
    fig.savefig(archivo, dpi=110)
    plt.close(fig)

    tiempo_total = time.perf_counter() - inicio
    print("=" * 68)
    print(" ESTADÍSTICAS DEL DASHBOARD")
    print("=" * 68)
    print(f" Total de documentos en el sistema: {total_docs:,}")
    print(f" 💾 Almacenamiento estimado: {almacenamiento_gb:.2f} GB")
    print(f" ⚡ Latencia promedio de consultas: {promedio_ms:.2f} ms")
    print(f" 💰 Costo mensual estimado: ${costo_mensual:,.2f}")
    print(f" 📈 Meses con datos: {meses_con_datos}")
    print(f" ⏱️  Generación en {tiempo_total:.2f} s")
    print("=" * 68)
    print(f"\n ✅ Dashboard generado exitosamente: {archivo.name}")
    print("    Abre el archivo PNG para ver el dashboard completo")
    client.close()


if __name__ == "__main__":
    generar_dashboard()