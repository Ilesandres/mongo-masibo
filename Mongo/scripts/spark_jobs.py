"""Spark Jobs (PySpark) — motor de procesamiento Big Data del proyecto.

Apache Spark procesa los datos ya preparados del Data Lake (zona CURATED)
y genera tablas listas para Business Intelligence / Data Warehouse.
Este script corresponde a la Fase 2 del curso: configuración de Spark,
≥3 transformaciones y generación de datos preparados.

Flujo:
    MongoDB → Data Lake (RAW/PROCESSED/CURATED) → Apache Spark → BI

Jobs adaptados al dominio Hyperflix:
    1. Consumo por dispositivo   → ¿qué dispositivo genera más consumo e ingresos?
    2. Segmentación de clientes  → ¿qué tipo de clientes tenemos? (VIP/Premium/Frecuente/Regular)
    3. Evolución mensual         → ¿cómo evoluciona el consumo por mes?

Requisito previo: Java (JVM) instalado con JAVA_HOME. Instalación:
    pip install pyspark
    winget install EclipseAdoptium.Temurin.17.JDK   # y reinicia la terminal

Ejecución:
    python Mongo/scripts/spark_jobs.py
"""

import glob
import os
import shutil
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # raíz (config)

import pyspark
from pyspark.sql import SparkSession
from pyspark.sql import functions as F

import config

# ── Bloque 2. Configuración para Windows (antes de crear la sesión) ──
os.environ.setdefault("PYSPARK_SUBMIT_ARGS", "--master local[*] pyspark-shell")
os.environ.setdefault("SPARK_LOCAL_HOSTNAME", "localhost")

CURATED = config.ZONAS_DATALAKE["curated"]
SALIDA_SPARK = CURATED / "spark"


def _verificar_java():
    """PySpark corre sobre la JVM: sin Java no puede iniciar SparkSession."""
    if shutil.which("java") is None and not os.environ.get("JAVA_HOME"):
        print("❌ No se encontró Java en el sistema.")
        print("   Apache Spark (PySpark) requiere una JVM. Instala OpenJDK 17 y define JAVA_HOME:")
        print("       winget install EclipseAdoptium.Temurin.17.JDK")
        print("   Después reinicia la terminal y vuelve a ejecutar este script.")
        sys.exit(1)


def _ultimo_parquet(sufijo):
    """Devuelve el Parquet más reciente de la zona CURATED que coincida con el sufijo.

    Evita escribir el nombre del archivo a mano: si cada día hay un snapshot
    nuevo, siempre trabaja con el último (idea del guion original con glob).
    """
    coincidencias = glob.glob(str(CURATED / f"{sufijo}*.parquet"))
    if not coincidencias:
        raise FileNotFoundError(f"No se encontró '{sufijo}*.parquet' en {CURATED}.")
    return max(coincidencias, key=os.path.getctime)


def _leer_curated(spark, sufijo):
    ruta = Path(_ultimo_parquet(sufijo)).as_uri()  # file:///C:/... evita bugs de URI en Windows
    print(f"  📂 Leyendo: {_ultimo_parquet(sufijo)}")
    return spark.read.parquet(ruta)


def _guardar_resultado(df_spark, nombre):
    SALIDA_SPARK.mkdir(parents=True, exist_ok=True)
    ruta = SALIDA_SPARK / f"{nombre}.parquet"
    df_spark.toPandas().to_parquet(
        ruta, engine=config.PARQUET_ENGINE, compression=config.PARQUET_COMPRESSION
    )
    print(f"  ✅ Guardado: {ruta} ({df_spark.count():,} filas)")


def crear_sesion():
    spark = (
        SparkSession.builder
        .appName(config.SPARK_APP_NAME)
        .master("local[*]")  # usa todos los núcleos del equipo
        .config("spark.sql.shuffle.partitions", "8")  # 1M filas repartidas entre 8 particiones
        .config("spark.driver.memory", "2g")
        .getOrCreate()
    )
    spark.sparkContext.setLogLevel("WARN")
    print(f"🚀 Apache Spark iniciado (pyspark {pyspark.__version__}) — distribuye el trabajo en {os.cpu_count()} núcleos.\n")
    return spark


# ── Spark Job 1 — Consumo por dispositivo ─────────────────
def job1_consumo_por_dispositivo(spark):
    """Responde: ¿qué dispositivo genera más consumo (y más ingresos)?"""
    print("═" * 70)
    print("📺 JOB 1 — Consumo por dispositivo")
    print("   Pregunta de negocio: ¿qué dispositivo genera más consumo e ingresos?")
    print("═" * 70)

    fact = _leer_curated(spark, "fact_reproduccion")
    resultado = (
        fact.groupBy("dispositivo")
        .agg(
            F.count("codigo_reproduccion").alias("reproducciones"),
            F.sum("minutos_visualizados").alias("minutos_totales"),
            F.sum("valor_estimado").alias("ingresos_totales"),
            F.avg("valor_estimado").alias("ingreso_promedio"),
        )
        .orderBy(F.col("ingresos_totales").desc())
    )
    resultado.show(20, truncate=False)
    _guardar_resultado(resultado, "consumo_por_dispositivo")


# ── Spark Job 2 — Segmentación de clientes ────────────────
def job2_segmentacion_clientes(spark):
    """Responde: ¿qué tipo de clientes tenemos? (según su consumo histórico)."""
    print("═" * 70)
    print("👥 JOB 2 — Segmentación de clientes")
    print("   Agrupa por usuario, calcula compras/gasto/ticket y clasifica con F.when.")
    print("═" * 70)

    fact = _leer_curated(spark, "fact_reproduccion")
    usuarios = _leer_curated(spark, "dim_usuario")

    por_usuario = (
        fact.groupBy("usuario_key")
        .agg(
            F.count("codigo_reproduccion").alias("reproducciones"),
            F.sum("minutos_visualizados").alias("minutos_totales"),
            F.sum("valor_estimado").alias("gasto_total"),
            F.avg("valor_estimado").alias("ticket_promedio"),
        )
    )

    segmentado = (
        por_usuario.join(usuarios.select("usuario_key", "nombre", "ciudad", "plan"), on="usuario_key", how="left")
        .withColumn(
            "segmento_cliente",
            F.when(F.col("gasto_total") >= config.SEGMENTO_VIP_MIN, "VIP")
            .when(F.col("gasto_total") >= config.SEGMENTO_PREMIUM_MIN, "Premium")
            .when(F.col("gasto_total") >= config.SEGMENTO_FRECUENTE_MIN, "Frecuente")
            .otherwise("Regular"),
        )
        .select(
            "usuario_key", "nombre", "ciudad", "plan",
            "reproducciones", "minutos_totales", "gasto_total", "ticket_promedio", "segmento_cliente",
        )
        .orderBy(F.col("gasto_total").desc())
    )

    print("   Top 10 clientes por consumo:")
    segmentado.show(10, truncate=False)

    print("   Distribución de segmentos: Regular | Frecuente | Premium | VIP")
    segmentado.groupBy("segmento_cliente").count().orderBy("count").show(truncate=False)

    _guardar_resultado(segmentado, "segmentacion_clientes")


# ── Spark Job 3 — Evolución mensual ───────────────────────
def job3_evolucion_mensual(spark):
    """Responde: ¿cómo evoluciona el consumo por mes? (alimenta dashboards de tendencia)."""
    print("═" * 70)
    print("📈 JOB 3 — Evolución mensual del consumo")
    print("   Descompone la fecha con to_date/year/month y agrega por año-mes.")
    print("═" * 70)

    fact = _leer_curated(spark, "fact_reproduccion")
    temporal = (
        fact.withColumn("fecha_ok", F.to_date("fecha_reproduccion"))
        .withColumn("anio", F.year("fecha_ok"))
        .withColumn("mes", F.month("fecha_ok"))
        .groupBy("anio", "mes")
        .agg(
            F.count("codigo_reproduccion").alias("reproducciones"),
            F.sum("minutos_visualizados").alias("minutos_totales"),
            F.sum("valor_estimado").alias("ingresos_totales"),
            F.sum("ganancia_estimada").alias("ganancia_total"),
        )
        .orderBy("anio", "mes")
    )
    temporal.show(60, truncate=False)
    _guardar_resultado(temporal, "evolucion_mensual")


# ── Ejecución principal ───────────────────────────────────
def ejecutar_jobs():
    _verificar_java()
    print("🔵 Apache Spark Jobs (Hyperflix) sobre la zona CURATED del Data Lake...\n")

    spark = crear_sesion()
    try:
        job1_consumo_por_dispositivo(spark)
        print()
        job2_segmentacion_clientes(spark)
        print()
        job3_evolucion_mensual(spark)

        print("\n✨ Spark Jobs finalizados. Resultados listos para BI en:")
        print(f"   {SALIDA_SPARK}")
    finally:
        spark.stop()
        print("\n✅ Spark detenido — memoria liberada.")


if __name__ == "__main__":
    ejecutar_jobs()