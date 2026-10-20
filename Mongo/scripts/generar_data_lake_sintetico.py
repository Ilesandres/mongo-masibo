# -*- coding: utf-8 -*-
"""Generador sintético del Data Lake (SIN MongoDB) — Hyperflix.

¿Por qué existe este script?
----------------------------
El clúster gratuito de MongoDB Atlas (**M0**) tiene un límite de ~512 MB. Con
volúmenes grandes (millones de reproducciones) la Fase 3 (`generar_datos_masivos.py`)
se queda corta: Atlas bloquea las escrituras con el error 8000 *"over your space
quota"*. Este script evita el problema de raíz: **no escribe nada en MongoDB**.

Genera los mismos documentos que `Mongo/scripts/generar_datos_masivos.py`
(reutiliza `Mongo/models/`) pero:
  * los produce **por lotes en memoria** (no se guarda todo el dataset),
  * los escribe como **Parquet** en un archivo temporal con `ParquetWriter`,
  * y al cerrar cada archivo lo **mueve al disco** o lo **sube a S3**, según
    `DATA_LAKE_BACKEND` (ver `Mongo/almacenamiento.py`).

Respeta exactamente la estructura y los datos de `Mongo/scripts/data_lake_pipeline.py`:

    RAW       : generos.parquet, directores.parquet, planes.parquet,
                usuarios.parquet, peliculas.parquet, suscripciones.parquet,
                pagos.parquet, resenas.parquet, reproducciones.parquet y
                reproducciones_analiticas.parquet (vista OLAP de la Fase 4)
    PROCESSED : reproducciones_procesadas.parquet, peliculas_procesadas.parquet,
                usuarios_procesados.parquet, suscripciones_procesadas.parquet,
                pagos_procesados.parquet, resenas_procesadas.parquet
    CURATED   : dim_usuario.parquet, dim_pelicula.parquet, dim_fecha.parquet,
                fact_reproduccion.parquet, analitica_temporal.parquet,
                analitica_contenido.parquet, analitica_cliente.parquet,
                analitica_pagos.parquet, analitica_resenas.parquet

Uso (desde la raíz del proyecto, con el venv activado):

    # Volúmenes de config.py, destino del .env (local o S3)
    python Mongo/scripts/generar_data_lake_sintetico.py

    # Sobrescribir volúmenes para apuntar a ~1 GB
    python Mongo/scripts/generar_data_lake_sintetico.py --reproducciones 5000000

    # Solo la zona RAW (más rápido, sin PROCESSED/CURATED)
    python Mongo/scripts/generar_data_lake_sintetico.py --solo-raw

    # Forzar disco local aunque el .env diga s3 (pruebas)
    #   PowerShell:  $env:DATA_LAKE_BACKEND="local"
    #   Linux/Mac:   DATA_LAKE_BACKEND=local python Mongo/scripts/...
"""
import argparse
import random
import sys
import tempfile
import time
import uuid
from datetime import datetime
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # raíz (config)
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # Mongo/ (models, almacenamiento)
sys.path.insert(0, str(Path(__file__).resolve().parent))      # scripts (data_lake_pipeline)

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
from bson import ObjectId

import almacenamiento
import config
import data_lake_pipeline as pipeline
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

# Columnas que forman la tabla de hechos (idénticas a data_lake_pipeline.py).
_COLUMNAS_FACT = [
    "codigo_reproduccion", "usuario_id", "pelicula_id", "fecha_reproduccion",
    "dispositivo", "calidad", "estado", "minutos_visualizados",
    "progreso_pct", "valor_estimado",
]


def _log(mensaje):
    print(mensaje, flush=True)


def _con_id(documento):
    """Añade un ``_id`` (hex de ObjectId) como haría MongoDB al insertar."""
    documento["_id"] = str(ObjectId())
    return documento


# ── Escritura Parquet por lotes (streaming a disco/S3) ─────
class EscritorParquet:
    """Escribe un Parquet incrementalmente y lo publica en el Data Lake al cerrar.

    El archivo se construye en un temporal local (un row-group por lote) para no
    mantener millones de filas en RAM. Al cerrar se mueve a ``data_lake/`` o se
    sube a S3 con `almacenamiento.publicar_parquet`.
    """

    def __init__(self, zona, nombre):
        self.zona = zona
        self.nombre = nombre
        self.temporal = Path(tempfile.gettempdir()) / f"hyperflix_{uuid.uuid4().hex}.parquet"
        self._writer = None
        self._schema = None
        self.filas = 0

    def escribir(self, df):
        if df is None or df.empty:
            return
        if self._schema is None:
            tabla = pa.Table.from_pandas(df, preserve_index=False)
            self._schema = tabla.schema
            self._writer = pq.ParquetWriter(
                str(self.temporal),
                self._schema,
                compression=config.PARQUET_COMPRESSION,
            )
        else:
            # Fuerza el mismo esquema del primer lote (evita rechazos de PyArrow).
            tabla = pa.Table.from_pandas(df, schema=self._schema, preserve_index=False)
        self._writer.write_table(tabla)
        self.filas += len(df)

    def cerrar(self):
        if self._writer is None:
            self.temporal.unlink(missing_ok=True)
            return None
        self._writer.close()
        destino = almacenamiento.publicar_parquet(self.temporal, self.zona, self.nombre)
        _log(f"  ✅ [{self.zona.upper()}] {self.nombre}.parquet -> {destino} ({self.filas:,} filas)")
        return destino


def _escribir_docs(zona, nombre, documentos, tamano_lote):
    """Escribe una lista de documentos como Parquet por lotes."""
    escritor = EscritorParquet(zona, nombre)
    for i in range(0, len(documentos), tamano_lote):
        escritor.escribir(pd.json_normalize(documentos[i:i + tamano_lote]))
    return escritor.cerrar()


def _lotes_parquet(zona, nombre, columnas=None, tamano_lote=None):
    """Itera un Parquet del Data Lake en lotes (descargándolo si está en S3)."""
    ruta_local = almacenamiento.materializar(almacenamiento.ruta(zona, nombre))
    archivo = pq.ParquetFile(ruta_local)
    for lote in archivo.iter_batches(batch_size=tamano_lote or config.BATCH_SIZE, columns=columnas):
        yield lote.to_pandas()


# ── Acumuladores para los agregados CURATED (streaming) ────
def _sumar(acumulador, df, claves, medidas):
    """Acumula sumas/conteos por clave sin guardar todos los hechos en memoria.

    ``medidas``: dict ``{nombre_salida: (columna, "sum" | "count")}``.
    """
    agregado = df.groupby(claves, as_index=False).agg(
        **{salida: (columna, funcion) for salida, (columna, funcion) in medidas.items()}
    )
    for fila in agregado.to_dict("records"):
        clave = tuple(fila[c] for c in claves)
        destino = acumulador.setdefault(clave, {m: 0.0 for m in medidas})
        for medida in medidas:
            destino[medida] += fila[medida]


def _acumulador_a_dataframe(acumulador, claves, orden=None):
    filas = []
    for clave, valores in acumulador.items():
        fila = dict(zip(claves, clave))
        fila.update(valores)
        filas.append(fila)
    df = pd.DataFrame(filas)
    if df.empty:
        return df
    if orden:
        df = df.sort_values(orden[0], ascending=orden[1]).reset_index(drop=True)
    return df


# ── Etapa 0: estructura de zonas ───────────────────────────
def crear_estructura():
    backend = almacenamiento.crear_estructura()
    if backend == "s3":
        _log(f"☁️ Data Lake en la nube (S3): s3://{config.S3_BUCKET}/{config.S3_PREFIX}".rstrip("/"))
    for zona in config.ZONAS_DATALAKE:
        _log(f"📁 Zona '{zona}' lista en: {almacenamiento.destino(zona)}")


# ── Etapa RAW: generación sintética (misma semántica que Fase 3) ──
def generar_raw(num_usuarios, num_peliculas, num_suscripciones, num_pagos,
                num_resenas, num_reproducciones, tamano_lote):
    _log("\n--- Etapa RAW: generación sintética (sin MongoDB) ---")

    # Catálogos
    generos = [_con_id(genero.generar(i)) for i in range(config.NUM_GENEROS)]
    directores = [_con_id(director.generar(i)) for i in range(config.NUM_DIRECTORES)]
    planes = [_con_id(plan.generar(i)) for i in range(config.NUM_PLANES)]
    _escribir_docs("raw", "generos", generos, tamano_lote)
    _escribir_docs("raw", "directores", directores, tamano_lote)
    _escribir_docs("raw", "planes", planes, tamano_lote)

    generos_codigos = [g["codigo_genero"] for g in generos]
    directores_codigos = [d["codigo_director"] for d in directores]
    genero_por_codigo = {g["codigo_genero"]: g["nombre"] for g in generos}
    director_por_codigo = {d["codigo_director"]: d["nombre"] for d in directores}
    nombres_plan = [p["nombre"] for p in planes]
    precio_por_plan = {p["codigo_plan"]: p["precio_mensual"] for p in planes}
    planes_precio = [{"codigo_plan": p["codigo_plan"], "precio_mensual": p["precio_mensual"]} for p in planes]

    # Usuarios: se conservan en memoria (contexto pequeño) para suscripciones/reproducciones.
    _log(f"👤 Generando {num_usuarios:,} usuarios...")
    usuarios = [
        _con_id(usuario.generar(i, plan=random.choice(nombres_plan)))
        for i in range(num_usuarios)
    ]
    _escribir_docs("raw", "usuarios", usuarios, tamano_lote)
    usuarios_ids = [u["_id"] for u in usuarios]
    usuarios_por_id = {u["_id"]: u for u in usuarios}
    usuarios_ctx = [{"_id": u["_id"], "fecha_registro": u["fecha_registro"]} for u in usuarios]

    # Películas
    _log(f"🎬 Generando {num_peliculas:,} películas...")
    peliculas = [
        _con_id(pelicula.generar(i, generos_codigos, directores_codigos))
        for i in range(num_peliculas)
    ]
    _escribir_docs("raw", "peliculas", peliculas, tamano_lote)
    peliculas_ids = [p["_id"] for p in peliculas]
    peliculas_por_id = {p["_id"]: p for p in peliculas}
    peliculas_ctx = [{"_id": p["_id"], "duracion_min": p["duracion_min"]} for p in peliculas]

    # Suscripciones
    _log(f"🔐 Generando {num_suscripciones:,} suscripciones...")
    suscripciones = [
        _con_id(suscripcion.generar(i, usuarios_ctx, planes))
        for i in range(num_suscripciones)
    ]
    _escribir_docs("raw", "suscripciones", suscripciones, tamano_lote)
    suscripciones_ctx = [
        {
            "_id": s["_id"],
            "codigo_plan": s["codigo_plan"],
            "precio_mensual": precio_por_plan[s["codigo_plan"]],
            "fecha_inicio": s["fecha_inicio"],
        }
        for s in suscripciones
    ]

    # Pagos (streaming: no se guarda la lista completa)
    _log(f"💳 Generando {num_pagos:,} pagos...")
    escritor_pagos = EscritorParquet("raw", "pagos")
    for base in range(0, num_pagos, tamano_lote):
        lote = [
            _con_id(pago.generar(base + i, suscripciones_ctx))
            for i in range(min(tamano_lote, num_pagos - base))
        ]
        escritor_pagos.escribir(pd.json_normalize(lote))
    escritor_pagos.cerrar()

    # Reseñas (streaming)
    _log(f"⭐ Generando {num_resenas:,} reseñas...")
    escritor_resenas = EscritorParquet("raw", "resenas")
    for base in range(0, num_resenas, tamano_lote):
        lote = [
            _con_id(resena.generar(base + i, usuarios_ids, peliculas_ids))
            for i in range(min(tamano_lote, num_resenas - base))
        ]
        escritor_resenas.escribir(pd.json_normalize(lote))
    escritor_resenas.cerrar()

    # Reproducciones + vista OLAP (misma estructura que transformar_oltp_a_olap.py)
    _log(f"📺 Generando {num_reproducciones:,} reproducciones (+ vista OLAP)...")
    escritor_rep = EscritorParquet("raw", "reproducciones")
    escritor_ana = EscritorParquet("raw", "reproducciones_analiticas")
    for base in range(0, num_reproducciones, tamano_lote):
        lote_rep = []
        lote_ana = []
        for i in range(min(tamano_lote, num_reproducciones - base)):
            doc = _con_id(reproduccion.generar(base + i, usuarios_ids, peliculas_ctx, config.TARIFA_POR_MINUTO))
            lote_rep.append(doc)

            usuario_doc = usuarios_por_id[doc["usuario_id"]]
            pelicula_doc = peliculas_por_id[doc["pelicula_id"]]
            fecha = doc["fecha_reproduccion"]
            lote_ana.append({
                "_id": doc["_id"],
                "fecha_reproduccion": fecha,
                "anio": fecha.year,
                "mes": fecha.month,
                "dia": fecha.day,
                "usuario": {
                    "id": usuario_doc["_id"],
                    "nombre": usuario_doc["nombre"],
                    "ciudad": usuario_doc["direccion"]["ciudad"],
                    "segmento": pipeline._segmento_por_valor(doc["valor_estimado"]),
                },
                "pelicula": {
                    "id": pelicula_doc["_id"],
                    "titulo": pelicula_doc["titulo"],
                    "genero": genero_por_codigo[pelicula_doc["genero_codigo"]],
                    "director": director_por_codigo[pelicula_doc["director_codigo"]],
                },
                "minutos_visualizados": doc["minutos_visualizados"],
                "valor_estimado": doc["valor_estimado"],
                "ganancia_estimada": doc["valor_estimado"] * config.MARGEN_GANANCIA,
                "codigo_reproduccion": doc["codigo_reproduccion"],
                "dispositivo": doc["dispositivo"],
                "calidad": doc["calidad"],
                "estado": doc["estado"],
            })
        escritor_rep.escribir(pd.json_normalize(lote_rep))
        escritor_ana.escribir(pd.json_normalize(lote_ana))
    escritor_rep.cerrar()
    escritor_ana.cerrar()


# ── Etapa PROCESSED: reproducciones (streaming) ────────────
def procesar_reproducciones(tamano_lote):
    _log("  → Reproducciones completadas + enriquecimiento (streaming)...")
    usuarios = almacenamiento.leer_parquet("raw", "usuarios")[
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
    peliculas = almacenamiento.leer_parquet("raw", "peliculas")[
        ["_id", "codigo_pelicula", "titulo", "genero_codigo", "director_codigo"]
    ].rename(columns={
        "_id": "pelicula_id",
        "codigo_pelicula": "pelicula_codigo",
        "titulo": "pelicula_titulo",
    })
    generos = almacenamiento.leer_parquet("raw", "generos")[["codigo_genero", "nombre"]].rename(
        columns={"codigo_genero": "genero_codigo_ref", "nombre": "pelicula_genero"}
    )
    directores = almacenamiento.leer_parquet("raw", "directores")[["codigo_director", "nombre"]].rename(
        columns={"codigo_director": "director_codigo_ref", "nombre": "pelicula_director"}
    )

    escritor = EscritorParquet("processed", "reproducciones_procesadas")
    leidas = 0
    for lote in _lotes_parquet("raw", "reproducciones", tamano_lote=tamano_lote):
        leidas += len(lote)
        df = lote[lote["estado"] == "Completada"].copy()
        if df.empty:
            continue
        df["fecha_dt"] = pd.to_datetime(df["fecha_reproduccion"], errors="coerce")
        df["anio"] = df["fecha_dt"].dt.year
        df["mes"] = df["fecha_dt"].dt.month
        df["dia"] = df["fecha_dt"].dt.day
        df["dia_semana"] = df["fecha_dt"].dt.dayofweek + 1
        df["trimestre"] = df["fecha_dt"].dt.quarter
        df["fecha_procesamiento"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        df["usuario_segmento"] = df["valor_estimado"].apply(pipeline._segmento_por_valor)

        df = df.merge(usuarios, on="usuario_id", how="left")
        df = df.merge(peliculas, on="pelicula_id", how="left")
        df = df.merge(generos, left_on="genero_codigo", right_on="genero_codigo_ref", how="left")
        df = df.merge(directores, left_on="director_codigo", right_on="director_codigo_ref", how="left")
        df.drop(columns=["fecha_dt", "genero_codigo_ref", "director_codigo_ref"], inplace=True, errors="ignore")
        escritor.escribir(df)
    escritor.cerrar()
    _log(f"  → Reproducciones leídas: {leidas:,} | completadas: {escritor.filas:,}")


# ── Etapa CURATED: modelo estrella + agregados (streaming) ──
def generar_curated(tamano_lote):
    _log("  → Construyendo dimensiones...")
    usuarios = almacenamiento.leer_parquet("processed", "usuarios_procesados")
    usuarios_dim = usuarios.copy()
    usuarios_dim["usuario_key"] = range(1, len(usuarios_dim) + 1)
    pipeline._guardar_parquet(usuarios_dim, "curated", "dim_usuario")

    peliculas = almacenamiento.leer_parquet("processed", "peliculas_procesadas")
    peliculas_dim = peliculas.copy()
    peliculas_dim["pelicula_key"] = range(1, len(peliculas_dim) + 1)
    pipeline._guardar_parquet(peliculas_dim, "curated", "dim_pelicula")

    # dim_fecha: fechas distintas de los hechos (solo Completadas).
    representantes = {}
    for lote in _lotes_parquet("processed", "reproducciones_procesadas",
                               columnas=["fecha_reproduccion"], tamano_lote=tamano_lote):
        normal = pd.to_datetime(lote["fecha_reproduccion"], errors="coerce").dt.normalize()
        pares = pd.DataFrame({"fecha": normal, "original": lote["fecha_reproduccion"]})
        for fila in pares.dropna().drop_duplicates("fecha").to_dict("records"):
            representantes.setdefault(fila["fecha"], fila["original"])
    fechas = pd.DataFrame(
        [{"fecha": f, "fecha_reproduccion": original}
         for f, original in sorted(representantes.items())]
    )
    fechas["fecha_key"] = range(1, len(fechas) + 1)
    fechas["anio"] = fechas["fecha"].dt.year
    fechas["mes"] = fechas["fecha"].dt.month
    fechas["dia"] = fechas["fecha"].dt.day
    fechas["dia_semana"] = fechas["fecha"].dt.dayofweek + 1
    fechas["trimestre"] = fechas["fecha"].dt.quarter
    fechas = fechas[[
        "fecha_reproduccion", "fecha", "fecha_key", "anio", "mes",
        "dia", "dia_semana", "trimestre",
    ]]
    pipeline._guardar_parquet(fechas, "curated", "dim_fecha")

    mapa_usuario = dict(zip(usuarios_dim["usuario_id"], usuarios_dim["usuario_key"]))
    mapa_pelicula = dict(zip(peliculas_dim["pelicula_id"], peliculas_dim["pelicula_key"]))
    mapa_fecha = dict(zip(fechas["fecha"], fechas["fecha_key"]))

    _log(f"  → Construyendo modelo estrella: {len(usuarios_dim):,} usuarios | "
         f"{len(peliculas_dim):,} películas | {len(fechas):,} fechas")

    escritor_fact = EscritorParquet("curated", "fact_reproduccion")
    acum_temporal = {}
    acum_contenido = {}
    acum_cliente = {}
    total_fact = 0

    for lote in _lotes_parquet("processed", "reproducciones_procesadas", tamano_lote=tamano_lote):
        fecha = pd.to_datetime(lote["fecha_reproduccion"], errors="coerce").dt.normalize()
        ganancia = (lote["valor_estimado"] * config.MARGEN_GANANCIA).round(2)

        fact = lote[_COLUMNAS_FACT].copy()
        fact["usuario_key"] = lote["usuario_id"].map(mapa_usuario)
        fact["pelicula_key"] = lote["pelicula_id"].map(mapa_pelicula)
        fact["fecha"] = fecha
        fact["fecha_key"] = fecha.map(mapa_fecha)
        fact["anio"] = fecha.dt.year
        fact["mes"] = fecha.dt.month
        fact["ganancia_estimada"] = ganancia
        fact.drop(columns=["fecha"], inplace=True)
        escritor_fact.escribir(fact)
        total_fact += len(fact)

        # Agregado mensual
        mensual = pd.DataFrame({
            "anio": fact["anio"],
            "mes": fact["mes"],
            "codigo_reproduccion": fact["codigo_reproduccion"],
            "minutos_visualizados": fact["minutos_visualizados"],
            "valor_estimado": fact["valor_estimado"],
            "ganancia_estimada": fact["ganancia_estimada"],
        })
        _sumar(acum_temporal, mensual, ["anio", "mes"], {
            "reproducciones": ("codigo_reproduccion", "count"),
            "minutos_totales": ("minutos_visualizados", "sum"),
            "ingresos_totales": ("valor_estimado", "sum"),
            "ganancia_total": ("ganancia_estimada", "sum"),
        })

        # Agregado por contenido (película)
        contenido = pd.DataFrame({
            "genero": lote["pelicula_genero"],
            "titulo": lote["pelicula_titulo"],
            "codigo_reproduccion": lote["codigo_reproduccion"],
            "minutos_visualizados": lote["minutos_visualizados"],
            "valor_estimado": lote["valor_estimado"],
        })
        _sumar(acum_contenido, contenido, ["genero", "titulo"], {
            "reproducciones": ("codigo_reproduccion", "count"),
            "ingresos_totales": ("valor_estimado", "sum"),
            "minutos_totales": ("minutos_visualizados", "sum"),
        })

        # Agregado por cliente (segmento + ciudad)
        cliente = pd.DataFrame({
            "segmento": lote["usuario_segmento"],
            "ciudad": lote["usuario_ciudad"],
            "codigo_reproduccion": lote["codigo_reproduccion"],
            "valor_estimado": lote["valor_estimado"],
            "ganancia_estimada": ganancia,
        })
        _sumar(acum_cliente, cliente, ["segmento", "ciudad"], {
            "reproducciones": ("codigo_reproduccion", "count"),
            "ingresos_totales": ("valor_estimado", "sum"),
            "ganancia_total": ("ganancia_estimada", "sum"),
            "suma_valor": ("valor_estimado", "sum"),
        })

    escritor_fact.cerrar()
    _log(f"  → Hechos escritos: {total_fact:,}")

    # analitica_temporal
    temporal = _acumulador_a_dataframe(acum_temporal, ["anio", "mes"], orden=(["anio", "mes"], [True, True]))
    pipeline._guardar_parquet(temporal, "curated", "analitica_temporal")

    # analitica_contenido
    contenido = _acumulador_a_dataframe(acum_contenido, ["genero", "titulo"])
    contenido = contenido.sort_values(["genero", "ingresos_totales"], ascending=[True, False]).reset_index(drop=True)
    pipeline._guardar_parquet(contenido, "curated", "analitica_contenido")

    # analitica_cliente
    cliente = _acumulador_a_dataframe(acum_cliente, ["segmento", "ciudad"])
    if not cliente.empty:
        cliente["valor_promedio"] = (cliente["suma_valor"] / cliente["reproducciones"]).round(6)
        cliente = cliente.drop(columns=["suma_valor"])
        cliente = cliente.sort_values("ingresos_totales", ascending=False).reset_index(drop=True)
    pipeline._guardar_parquet(cliente, "curated", "analitica_cliente")

    # analitica_pagos / analitica_resenas (volumen medio: misma lógica que el pipeline)
    pagos = almacenamiento.leer_parquet("processed", "pagos_procesados")
    analitica_pagos = pagos.groupby(["anio", "mes", "estado"], as_index=False).agg(
        total_recaudado=("monto", "sum"),
        numero_pagos=("codigo_pago", "count"),
    ).sort_values(["anio", "mes"])
    pipeline._guardar_parquet(analitica_pagos, "curated", "analitica_pagos")

    resenas = almacenamiento.leer_parquet("processed", "resenas_procesadas")
    analitica_resenas = resenas.groupby(["genero"], as_index=False).agg(
        numero_resenas=("codigo_resena", "count"),
        puntuacion_promedio=("puntuacion", "mean"),
        puntuacion_minima=("puntuacion", "min"),
        puntuacion_maxima=("puntuacion", "max"),
    ).sort_values("puntuacion_promedio", ascending=False)
    pipeline._guardar_parquet(analitica_resenas, "curated", "analitica_resenas")


# ── Orquestador ────────────────────────────────────────────
def _parsear_argumentos():
    parser = argparse.ArgumentParser(
        description="Genera el Data Lake completo (RAW/PROCESSED/CURATED) sin usar MongoDB.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--reproducciones", type=int, default=config.NUM_REPRODUCCIONES,
                        help="Cantidad de reproducciones a generar")
    parser.add_argument("--usuarios", type=int, default=config.NUM_USUARIOS)
    parser.add_argument("--peliculas", type=int, default=config.NUM_PELICULAS)
    parser.add_argument("--suscripciones", type=int, default=config.NUM_SUSCRIPCIONES)
    parser.add_argument("--pagos", type=int, default=config.NUM_PAGOS)
    parser.add_argument("--resenas", type=int, default=config.NUM_RESENAS)
    parser.add_argument("--batch-size", type=int, default=config.BATCH_SIZE,
                        help="Filas por lote en memoria")
    parser.add_argument("--semilla", type=int, default=42, help="Semilla de aleatoriedad")
    parser.add_argument("--solo-raw", action="store_true",
                        help="Genera solo la zona RAW (omite PROCESSED/CURATED)")
    return parser.parse_args()


def main():
    args = _parsear_argumentos()
    random.seed(args.semilla)

    _log("🚀 Generador sintético del Data Lake (Hyperflix) — SIN MongoDB")
    _log(f"   Destino: {almacenamiento.backend().upper()} | lotes de {args.batch_size:,} filas")
    _log(f"   Volúmenes: {args.reproducciones:,} reproducciones, {args.usuarios:,} usuarios, "
         f"{args.peliculas:,} películas")

    inicio = time.time()
    crear_estructura()

    generar_raw(
        num_usuarios=args.usuarios,
        num_peliculas=args.peliculas,
        num_suscripciones=args.suscripciones,
        num_pagos=args.pagos,
        num_resenas=args.resenas,
        num_reproducciones=args.reproducciones,
        tamano_lote=args.batch_size,
    )

    if args.solo_raw:
        _log("\n⏭️  --solo-raw: se omite PROCESSED/CURATED.")
    else:
        _log("\n--- Etapa PROCESSED: limpieza y enriquecimiento ---")
        procesar_reproducciones(args.batch_size)
        # Catálogos pequeños: se reutiliza la lógica exacta de la Fase 6.
        pipeline.procesar_catalogos()

        _log("\n--- Etapa CURATED: modelo estrella y agregados ---")
        generar_curated(args.batch_size)

    pipeline.mostrar_resumen_lake()
    _log(f"\n✨ Generación completada en {time.time() - inicio:.1f}s.")


if __name__ == "__main__":
    main()
