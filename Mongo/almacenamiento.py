# -*- coding: utf-8 -*-
"""almacenamiento.py — Abstracción de almacenamiento del Data Lake.

El pipeline de Data Lake (Fase 6) y los Spark Jobs (Fase 8) NO escriben rutas
"a mano": siempre pasan por este módulo. Según ``DATA_LAKE_BACKEND`` en el
``.env`` la MISMA línea de código apunta al disco o a la nube:

    DATA_LAKE_BACKEND=local  ->  Mongo/data_lake/{zona}/...            (por defecto)
    DATA_LAKE_BACKEND=s3     ->  s3://{S3_BUCKET}/{S3_PREFIX}/{zona}/...

En S3, pandas lee y escribe Parquet directamente a través de ``s3fs``:

    df.to_parquet("s3://mi-bucket/raw/usuarios.parquet")

De esta forma el código corre igual en el laboratorio (PC) o contra un Data
Lake real en la nube (Amazon S3, MinIO, cualquier servicio compatible) sin
cambiar los pipelines.

Variables del ``.env`` que usa:
    DATA_LAKE_BACKEND   local | s3
    S3_BUCKET           nombre del bucket (obligatorio si backend=s3)
    S3_PREFIX           carpeta raíz dentro del bucket (opcional, ej. "hyperflix")
    AWS_REGION          región del bucket (ej. us-east-1)
    AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY [/ AWS_SESSION_TOKEN]
    S3_ENDPOINT_URL     solo para MinIO u otro S3-compatible (vacío = AWS)
"""
import glob
import os
import re
from pathlib import Path

import pandas as pd

import config

# Regiones válidas: us-east-1, us-east-2, eu-west-1, ap-southeast-2, us-gov-west-1...
_REGION_VALIDA = re.compile(r"^[a-z]{2}(-gov)?-[a-z]+-\d$")


# ── Backend ────────────────────────────────────────────────
def es_s3():
    """¿El Data Lake apunta a Amazon S3 (u otro S3-compatible)?"""
    return config.DATA_LAKE_BACKEND == "s3"


def backend():
    return "s3" if es_s3() else "local"


def _prefijo(zona):
    """Carpeta lógica de una zona dentro del bucket (incluye S3_PREFIX si existe)."""
    partes = [p for p in (config.S3_PREFIX, zona) if p]
    return "/".join(partes)


def _verificar_s3():
    if not config.S3_BUCKET:
        raise RuntimeError(
            "DATA_LAKE_BACKEND=s3 pero falta S3_BUCKET en el .env. "
            "Rellena S3_BUCKET (y las credenciales AWS) antes de continuar."
        )
    if config.AWS_REGION and not _REGION_VALIDA.match(config.AWS_REGION):
        raise RuntimeError(
            f"AWS_REGION='{config.AWS_REGION}' no es una región válida (ej. us-east-1, "
            "us-east-2, eu-west-1). Revisa el .env: un valor mal escrito provoca "
            "'Access Denied' al firmar las peticiones."
        )


def storage_options():
    """Opciones de conexión para pandas/s3fs (se usan solo en las llamadas a S3)."""
    opciones = {}
    if config.AWS_ACCESS_KEY_ID:
        opciones["key"] = config.AWS_ACCESS_KEY_ID
    if config.AWS_SECRET_ACCESS_KEY:
        opciones["secret"] = config.AWS_SECRET_ACCESS_KEY
    if config.AWS_SESSION_TOKEN:
        opciones["token"] = config.AWS_SESSION_TOKEN
    if config.AWS_REGION:
        opciones["client_kwargs"] = {"region_name": config.AWS_REGION}
    if config.S3_ENDPOINT_URL:
        opciones["endpoint_url"] = config.S3_ENDPOINT_URL
        # MinIO y otros S3-compatibles exigen direccionamiento por ruta (no virtual-host).
        opciones["config_kwargs"] = {"s3": {"addressing_style": "path"}}
    return opciones


def _s3fs():
    try:
        import s3fs
    except ImportError as error:
        raise RuntimeError(
            "Falta la librería 's3fs' para hablar con S3. Instálala con: "
            "pip install -r requirements.txt"
        ) from error
    return s3fs.S3FileSystem(**(storage_options() or {}))


# ── Rutas ──────────────────────────────────────────────────
def ruta(zona, nombre):
    """Ruta/URI destino de un objeto del Data Lake (str).

    ``nombre`` admite subcarpeta lógica, p. ej. ``"spark/evolucion_mensual"``.
    """
    if es_s3():
        return f"s3://{config.S3_BUCKET}/{_prefijo(zona)}/{nombre}.parquet"
    return str(config.ZONAS_DATALAKE[zona] / f"{nombre}.parquet")


def destino(zona):
    """Descripción legible del origen/destino de una zona."""
    if es_s3():
        return f"s3://{config.S3_BUCKET}/{_prefijo(zona)}/"
    return str(config.ZONAS_DATALAKE[zona])


# ── Lectura / escritura Parquet ────────────────────────────
def escribir_parquet(df, zona, nombre):
    """Guarda un DataFrame como Parquet (Snappy) en la zona indicada.

    Devuelve la ruta/URI donde quedó el archivo.
    """
    if es_s3():
        _verificar_s3()
    destino_archivo = ruta(zona, nombre)
    if es_s3():
        df.to_parquet(
            destino_archivo,
            engine=config.PARQUET_ENGINE,
            compression=config.PARQUET_COMPRESSION,
            storage_options=storage_options(),
        )
    else:
        Path(destino_archivo).parent.mkdir(parents=True, exist_ok=True)
        df.to_parquet(
            destino_archivo,
            engine=config.PARQUET_ENGINE,
            compression=config.PARQUET_COMPRESSION,
        )
    return destino_archivo


def leer_parquet(zona, nombre):
    """Lee un Parquet de la zona indicada, sin importar si está en disco o en S3."""
    origen = ruta(zona, nombre)
    if es_s3():
        _verificar_s3()
        return pd.read_parquet(origen, storage_options=storage_options())
    return pd.read_parquet(origen)


# ── Localizadores (para Spark / scripts que necesitan el más reciente) ──
def ultimo_parquet(zona, sufijo):
    """Ruta (local o ``s3://``) del ``.parquet`` más reciente que empiece con ``sufijo``."""
    if es_s3():
        _verificar_s3()
        fs = _s3fs()
        base = f"{config.S3_BUCKET}/{_prefijo(zona)}"
        coincidencias = []
        for objeto in fs.find(base):
            if not objeto.endswith(".parquet"):
                continue
            relativo = objeto[len(base):].lstrip("/")
            if relativo.startswith(sufijo):
                coincidencias.append(objeto)
        if not coincidencias:
            raise FileNotFoundError(f"No se encontró '{sufijo}*.parquet' en s3://{base}/.")
        ultimo = max(coincidencias, key=lambda o: (fs.info(o).get("LastModified") or fs.info(o).get("mtime") or 0))
        return f"s3://{ultimo}"

    base_local = config.ZONAS_DATALAKE[zona]
    coincidencias = glob.glob(str(base_local / f"{sufijo}*.parquet"))
    if not coincidencias:
        raise FileNotFoundError(f"No se encontró '{sufijo}*.parquet' en {base_local}.")
    return max(coincidencias, key=os.path.getctime)


def materializar(uri):
    """Si ``uri`` es ``s3://``, lo descarga a un caché local y devuelve la ruta local.

    Si ya es una ruta local, la devuelve sin cambios. Sirve para que Apache Spark
    (que no entiende ``s3://`` sin los jars de Hadoop) lea un archivo local.
    """
    if not uri.startswith("s3://"):
        return uri
    _verificar_s3()
    cache = config.DATA_LAKE_ROOT / ".cache_s3"
    cache.mkdir(parents=True, exist_ok=True)
    destino_local = cache / uri.rsplit("/", 1)[-1]
    _s3fs().get(uri, str(destino_local))
    return str(destino_local)


# ── Provisionamiento e inventario ──────────────────────────
def crear_estructura():
    """Crea las zonas del Data Lake (discos locales) o verifica/crea el bucket (S3).

    Devuelve el backend usado.
    """
    if es_s3():
        _verificar_s3()
        fs = _s3fs()
        if not fs.exists(config.S3_BUCKET):
            raise RuntimeError(
                f"El bucket s3://{config.S3_BUCKET} no existe o no tienes acceso. "
                "Créalo en la consola de AWS (o con 'aws s3 mb') y revisa tus credenciales."
            )
        for zona in config.ZONAS_DATALAKE:
            prefijo = f"{config.S3_BUCKET}/{_prefijo(zona)}"
            if not fs.exists(prefijo):
                fs.makedirs(prefijo, exist_ok=True)
        return "s3"

    for ruta_zona in config.ZONAS_DATALAKE.values():
        Path(ruta_zona).mkdir(parents=True, exist_ok=True)
    return "local"


def listar_zona(zona):
    """Devuelve ``[(nombre_archivo, tamanio_bytes), ...]`` de los Parquet de una zona."""
    if es_s3():
        _verificar_s3()
        fs = _s3fs()
        base = f"{config.S3_BUCKET}/{_prefijo(zona)}"
        try:
            objetos = fs.find(base)
        except FileNotFoundError:
            return []
        return [
            (o.rsplit("/", 1)[-1], fs.info(o).get("size", 0))
            for o in objetos
            if o.endswith(".parquet")
        ]

    carpeta = config.ZONAS_DATALAKE[zona]
    if not Path(carpeta).exists():
        return []
    return [
        (f, os.path.getsize(Path(carpeta) / f))
        for f in os.listdir(carpeta)
        if f.endswith(".parquet")
    ]


def inventario():
    """Total de archivos/tamaño del Data Lake y el detalle por zona.

    Devuelve ``(total_archivos, total_bytes, {zona: (n_archivos, bytes)})``.
    """
    total_archivos = 0
    total_bytes = 0
    por_zona = {}
    for zona in config.ZONAS_DATALAKE:
        archivos = listar_zona(zona)
        tamanio = sum(t for _, t in archivos)
        por_zona[zona] = (len(archivos), tamanio)
        total_archivos += len(archivos)
        total_bytes += tamanio
    return total_archivos, total_bytes, por_zona
