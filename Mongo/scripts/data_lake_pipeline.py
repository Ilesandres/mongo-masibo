# -*- coding: utf-8 -*-
"""Fase 6 — Pipeline del Data Lake (RAW → PROCESSED → CURATED).

Exporta MongoDB a Parquet (Snappy) en tres zonas y construye el modelo estrella
listo para BI. El destino lo decide el ``.env`` a través de `almacenamiento`:

    DATA_LAKE_BACKEND=local  ->  Mongo/data_lake/{raw,processed,curated}/
    DATA_LAKE_BACKEND=s3     ->  s3://{S3_BUCKET}/{S3_PREFIX}/{zona}/

Es decir, el mismo pipeline corre en el disco o sube los Parquet directamente
a Amazon S3 (Data Lake real en la nube) sin cambiar el código.

    python Mongo/scripts/data_lake_pipeline.py
"""
import sys
import time
from datetime import datetime
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # raíz (config)
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # Mongo/ (almacenamiento)

import pymongo
import pandas as pd
from bson import ObjectId

import almacenamiento
import config


def _log(mensaje):
    """Imprime con flush para que el estado sea visible en consola en tiempo real."""
    print(mensaje, flush=True)


# ── Utilidades ─────────────────────────────────────────────
# La lectura/escritura pasa por `almacenamiento`, que decide si el Data Lake
# vive en el disco (local) o en la nube (s3://...) según el .env.
def _ruta(zona, nombre):
    return almacenamiento.ruta(zona, nombre)


def _guardar_parquet(df, zona, nombre):
    destino = almacenamiento.escribir_parquet(df, zona, nombre)
    _log(f"  ✅ [{zona.upper()}] {nombre}.parquet -> {destino} ({len(df)} filas)")
    return destino


def _leer_parquet(zona, nombre):
    return almacenamiento.leer_parquet(zona, nombre)


def _segmento_por_valor(valor):
    if valor >= config.SEGMENTO_COMPLETO_MIN:
        return "Completo"
    if valor >= config.SEGMENTO_PARCIAL_MIN:
        return "Parcial"
    return "Corto"


# ── Bloque 3: estructura de zonas ──────────────────────────
def crear_estructura_lake():
    backend = almacenamiento.crear_estructura()
    if backend == "s3":
        _log(f"☁️ Data Lake en la nube (S3): s3://{config.S3_BUCKET}/{config.S3_PREFIX}".rstrip("/"))
    for zona in config.ZONAS_DATALAKE:
        _log(f"📁 Zona '{zona}' creada/verificada en: {almacenamiento.destino(zona)}")


# ── Etapa RAW: copia exacta de MongoDB → Parquet ───────────
def _convertir_objectids_a_str(df):
    """Convierte columnas de tipo ObjectId (incluidas referencias anidadas) a str.

    Parquet no entiende el tipo ObjectId de BSON; se serializa como su valor hex.
    """
    for col in df.columns:
        if df[col].dtype == object:
            valores = df[col].dropna()
            if len(valores) > 0 and isinstance(valores.iloc[0], ObjectId):
                df[col] = df[col].astype(str)
    return df


def exportar_raw(db, coleccion):
    _log(f"  ⬇️ Exportando '{coleccion}'...")
    inicio = time.perf_counter()
    documentos = list(db[coleccion].find({}, batch_size=2_000))
    _log(f"     {len(documentos)} documentos leídos en {time.perf_counter() - inicio:.1f}s")
    if not documentos:
        _log(f"  ⚠️ Colección '{coleccion}' vacía; se omite.")
        return None

    df = pd.json_normalize(documentos)
    df = _convertir_objectids_a_str(df)
    _guardar_parquet(df, "raw", coleccion)


# ── Etapa PROCESSED: limpieza y enriquecimiento ────────────
def procesar_reproducciones():
    """Hecho transaccional enriquecido (equivalente a 'ventas_procesadas')."""
    df = _leer_parquet("raw", "reproducciones")
    total_leidas = len(df)
    df = df[df["estado"] == "Completada"].copy()
    _log(f"  → Reproducciones leídas: {total_leidas} | completadas: {len(df)}")
    if df.empty:
        _log("  ⚠️ No hay reproducciones completadas para procesar.")
        return None

    df["fecha_dt"] = pd.to_datetime(df["fecha_reproduccion"], errors="coerce")
    df["anio"] = df["fecha_dt"].dt.year
    df["mes"] = df["fecha_dt"].dt.month
    df["dia"] = df["fecha_dt"].dt.day
    df["dia_semana"] = df["fecha_dt"].dt.dayofweek + 1
    df["trimestre"] = df["fecha_dt"].dt.quarter
    df["fecha_procesamiento"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    df["usuario_segmento"] = df["valor_estimado"].apply(_segmento_por_valor)

    usuarios = _leer_parquet("raw", "usuarios")[
        ["_id", "codigo_usuario", "nombre", "direccion.ciudad", "direccion.pais", "plan", "activo"]
    ].rename(columns={
        "_id": "usuario_id",
        "codigo_usuario": "usuario_codigo",
        "nombre": "usuario_nombre",
        "direccion.ciudad": "usuario_ciudad",
        "direccion.pais": "usuario_pais",
        "plan": "usuario_plan",
        "activo": "usuario_activo",
    })
    df = df.merge(usuarios, on="usuario_id", how="left")

    peliculas = _leer_parquet("raw", "peliculas")[
        ["_id", "codigo_pelicula", "titulo", "genero_codigo", "director_codigo"]
    ].rename(columns={
        "_id": "pelicula_id",
        "codigo_pelicula": "pelicula_codigo",
        "titulo": "pelicula_titulo",
    })
    df = df.merge(peliculas, on="pelicula_id", how="left")

    generos = _leer_parquet("raw", "generos")[["codigo_genero", "nombre"]].rename(
        columns={"codigo_genero": "genero_codigo_ref", "nombre": "pelicula_genero"}
    )
    df = df.merge(generos, left_on="genero_codigo", right_on="genero_codigo_ref", how="left")

    directores = _leer_parquet("raw", "directores")[["codigo_director", "nombre"]].rename(
        columns={"codigo_director": "director_codigo_ref", "nombre": "pelicula_director"}
    )
    df = df.merge(directores, left_on="director_codigo", right_on="director_codigo_ref", how="left")

    df.drop(columns=["fecha_dt", "genero_codigo_ref", "director_codigo_ref"], inplace=True, errors="ignore")
    _guardar_parquet(df, "processed", "reproducciones_procesadas")
    return df


def procesar_catalogos():
    """Catálogos limpios con referencias resueltas."""
    _log("  → Procesando catálogos (películas, usuarios, suscripciones, pagos, reseñas)...")
    generos = _leer_parquet("raw", "generos")
    directores = _leer_parquet("raw", "directores")
    planes = _leer_parquet("raw", "planes")

    pelis = _leer_parquet("raw", "peliculas")
    pelis = pelis.merge(
        generos[["codigo_genero", "nombre"]].rename(columns={"nombre": "genero"}),
        left_on="genero_codigo", right_on="codigo_genero", how="left",
    ).merge(
        directores[["codigo_director", "nombre"]].rename(columns={"nombre": "director"}),
        left_on="director_codigo", right_on="codigo_director", how="left",
    )
    pelis.rename(columns={"_id": "pelicula_id"}, inplace=True)
    _guardar_parquet(pelis, "processed", "peliculas_procesadas")

    usr = _leer_parquet("raw", "usuarios")
    usr.rename(columns={"_id": "usuario_id"}, inplace=True)
    usr["ciudad"] = usr["direccion.ciudad"]
    usr["pais"] = usr["direccion.pais"]
    usr["antiguedad_meses"] = (datetime.now() - pd.to_datetime(usr["fecha_registro"])).dt.days // 30
    usr.drop(columns=["direccion.calle", "direccion.ciudad", "direccion.pais"], inplace=True)
    _guardar_parquet(usr, "processed", "usuarios_procesados")

    sus = _leer_parquet("raw", "suscripciones")
    sus = sus.merge(
        planes[["codigo_plan", "nombre", "precio_mensual"]].rename(columns={"nombre": "plan_nombre"}),
        on="codigo_plan", how="left",
    )
    sus["anio_inicio"] = pd.to_datetime(sus["fecha_inicio"]).dt.year
    sus["mes_inicio"] = pd.to_datetime(sus["fecha_inicio"]).dt.month
    _guardar_parquet(sus, "processed", "suscripciones_procesadas")

    pagos = _leer_parquet("raw", "pagos")
    pagos = pagos.merge(
        sus[["_id", "usuario_id", "codigo_plan"]], left_on="suscripcion_id", right_on="_id", how="left"
    )
    pagos["anio"] = pd.to_datetime(pagos["fecha_pago"]).dt.year
    pagos["mes"] = pd.to_datetime(pagos["fecha_pago"]).dt.month
    _guardar_parquet(pagos, "processed", "pagos_procesados")

    resenas = _leer_parquet("raw", "resenas")
    resenas = resenas.merge(
        pelis[["pelicula_id", "titulo", "genero", "director"]],
        on="pelicula_id", how="left",
    )
    resenas["puntuacion_categoria"] = pd.cut(
        resenas["puntuacion"], bins=[0, 2, 3, 5], labels=["Crítica", "Neutral", "Positiva"]
    )
    _guardar_parquet(resenas, "processed", "resenas_procesadas")


# ── Etapa CURATED: modelo estrella + agregados BI ──────────
def _generar_modelo_estrella():
    facts = _leer_parquet("processed", "reproducciones_procesadas")
    usuarios = _leer_parquet("processed", "usuarios_procesados")
    peliculas = _leer_parquet("processed", "peliculas_procesadas")
    _log(f"  → Construyendo modelo estrella: {len(facts)} hechos | {len(usuarios)} usuarios | {len(peliculas)} películas")

    usuarios_dim = usuarios.copy()
    usuarios_dim["usuario_key"] = range(1, len(usuarios_dim) + 1)
    _guardar_parquet(usuarios_dim, "curated", "dim_usuario")

    peliculas_dim = peliculas.copy()
    peliculas_dim["pelicula_key"] = range(1, len(peliculas_dim) + 1)
    _guardar_parquet(peliculas_dim, "curated", "dim_pelicula")

    fechas = facts[["fecha_reproduccion"]].drop_duplicates()
    fechas["fecha"] = pd.to_datetime(fechas["fecha_reproduccion"]).dt.normalize()
    fechas = fechas.drop_duplicates("fecha").reset_index(drop=True)
    fechas["fecha_key"] = range(1, len(fechas) + 1)
    fechas["anio"] = fechas["fecha"].dt.year
    fechas["mes"] = fechas["fecha"].dt.month
    fechas["dia"] = fechas["fecha"].dt.day
    fechas["dia_semana"] = fechas["fecha"].dt.dayofweek + 1
    fechas["trimestre"] = fechas["fecha"].dt.quarter
    _guardar_parquet(fechas, "curated", "dim_fecha")

    fact = facts[[
        "codigo_reproduccion", "usuario_id", "pelicula_id", "fecha_reproduccion",
        "dispositivo", "calidad", "estado", "minutos_visualizados",
        "progreso_pct", "valor_estimado",
    ]].merge(
        usuarios_dim[["usuario_id", "usuario_key"]], on="usuario_id", how="left"
    ).merge(
        peliculas_dim[["pelicula_id", "pelicula_key"]], on="pelicula_id", how="left"
    )
    fact["fecha"] = pd.to_datetime(fact["fecha_reproduccion"]).dt.normalize()
    fact = fact.merge(fechas[["fecha", "fecha_key", "anio", "mes"]], on="fecha", how="left")
    fact["ganancia_estimada"] = (fact["valor_estimado"] * config.MARGEN_GANANCIA).round(2)
    fact.drop(columns=["fecha"], inplace=True)
    _guardar_parquet(fact, "curated", "fact_reproduccion")
    return fact, usuarios_dim, peliculas_dim


def _generar_agregados(fact, usuarios_dim, peliculas_dim):
    analitica_temporal = fact.groupby(["anio", "mes"], as_index=False).agg(
        reproducciones=("codigo_reproduccion", "count"),
        minutos_totales=("minutos_visualizados", "sum"),
        ingresos_totales=("valor_estimado", "sum"),
        ganancia_total=("ganancia_estimada", "sum"),
    ).sort_values(["anio", "mes"])
    _guardar_parquet(analitica_temporal, "curated", "analitica_temporal")

    fact_peli = fact.merge(
        peliculas_dim[["pelicula_key", "titulo", "genero", "director"]],
        on="pelicula_key", how="left",
    )
    analitica_contenido = fact_peli.groupby(["genero", "titulo"], as_index=False).agg(
        reproducciones=("codigo_reproduccion", "count"),
        ingresos_totales=("valor_estimado", "sum"),
        minutos_totales=("minutos_visualizados", "sum"),
    ).sort_values(["genero", "ingresos_totales"], ascending=[True, False])
    _guardar_parquet(analitica_contenido, "curated", "analitica_contenido")

    fact_usr = fact.merge(
        usuarios_dim[["usuario_key", "ciudad", "plan"]], on="usuario_key", how="left"
    )
    fact_usr["segmento"] = fact_usr["valor_estimado"].apply(_segmento_por_valor)
    analitica_cliente = fact_usr.groupby(["segmento", "ciudad"], as_index=False).agg(
        reproducciones=("codigo_reproduccion", "count"),
        ingresos_totales=("valor_estimado", "sum"),
        ganancia_total=("ganancia_estimada", "sum"),
        valor_promedio=("valor_estimado", "mean"),
    ).sort_values("ingresos_totales", ascending=False)
    _guardar_parquet(analitica_cliente, "curated", "analitica_cliente")

    pagos = _leer_parquet("processed", "pagos_procesados")
    analitica_pagos = pagos.groupby(["anio", "mes", "estado"], as_index=False).agg(
        total_recaudado=("monto", "sum"),
        numero_pagos=("codigo_pago", "count"),
    ).sort_values(["anio", "mes"])
    _guardar_parquet(analitica_pagos, "curated", "analitica_pagos")

    resenas = _leer_parquet("processed", "resenas_procesadas")
    analitica_resenas = resenas.groupby(["genero"], as_index=False).agg(
        numero_resenas=("codigo_resena", "count"),
        puntuacion_promedio=("puntuacion", "mean"),
        puntuacion_minima=("puntuacion", "min"),
        puntuacion_maxima=("puntuacion", "max"),
    ).sort_values("puntuacion_promedio", ascending=False)
    _guardar_parquet(analitica_resenas, "curated", "analitica_resenas")


# ── Bloque 7: resumen del data lake ────────────────────────
def mostrar_resumen_lake():
    _log(f"\n--- Bloque 7. Resumen del Data Lake (backend: {almacenamiento.backend()}) ---")
    total_archivos, total_bytes, por_zona = almacenamiento.inventario()
    for zona, (n_archivos, tamanio) in por_zona.items():
        _log(f"  {zona.upper()}: {n_archivos} archivo(s) | {tamanio / 1024:.1f} KB")
    _log(f"  TOTAL: {total_archivos} archivos | {total_bytes / 1024:.1f} KB ({total_bytes / (1024 * 1024):.2f} MB)")


# ── Orquestador ────────────────────────────────────────────
def generar_data_lake_completo():
    _log("🚀 Iniciando pipeline de Data Lake (Hyperflix)...")
    crear_estructura_lake()

    client = pymongo.MongoClient(config.MONGO_URI)
    db = client[config.DB_NAME]

    _log("\n--- Etapa RAW: exportación exacta de MongoDB ---")
    for col in config.COLECCIONES_DATALAKE:
        exportar_raw(db, col)

    _log("\n--- Etapa PROCESSED: limpieza y enriquecimiento ---")
    procesar_reproducciones()
    procesar_catalogos()

    _log("\n--- Etapa CURATED: modelo estrella y agregados ---")
    fact, usuarios_dim, peliculas_dim = _generar_modelo_estrella()
    _generar_agregados(fact, usuarios_dim, peliculas_dim)

    mostrar_resumen_lake()
    _log("\n✨ Pipeline de Data Lake finalizado con éxito.")
    client.close()


if __name__ == "__main__":
    generar_data_lake_completo()