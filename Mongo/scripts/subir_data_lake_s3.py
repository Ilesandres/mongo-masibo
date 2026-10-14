# -*- coding: utf-8 -*-
"""Sube el Data Lake local (Mongo/data_lake) a un bucket de Amazon S3.

Sirve para migrar los Parquet ya generados en el disco a la nube **sin volver a
correr las Fases 3-6**. Es el paso que se hace una sola vez cuando se pasa a
`DATA_LAKE_BACKEND=s3`.

Requisitos en `taller-conexion-mongo/.env`:
    S3_BUCKET=mi-bucket
    AWS_ACCESS_KEY_ID=...
    AWS_SECRET_ACCESS_KEY=...
    AWS_REGION=us-east-1
    # opcionales
    S3_PREFIX=hyperflix            # carpeta raíz dentro del bucket
    S3_ENDPOINT_URL=               # MinIO u otro S3-compatible (vacío = AWS)

Ejecución:
    python Mongo/scripts/subir_data_lake_s3.py
"""
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # raíz (config)
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # Mongo/ (almacenamiento)

import almacenamiento
import config


def _log(mensaje):
    print(mensaje, flush=True)


def subir_data_lake():
    if not config.S3_BUCKET:
        _log("❌ Falta S3_BUCKET en el .env. Rellena el bloque de Amazon S3 y vuelve a intentar.")
        sys.exit(1)

    import s3fs

    fs = s3fs.S3FileSystem(**(almacenamiento.storage_options() or {}))
    bucket = config.S3_BUCKET
    if not fs.exists(bucket):
        _log(f"❌ El bucket s3://{bucket} no existe o no tienes acceso con estas credenciales.")
        sys.exit(1)

    objetivo = f"s3://{bucket}" + (f"/{config.S3_PREFIX}" if config.S3_PREFIX else "")
    _log(f"☁️ Subiendo el Data Lake local a {objetivo}")

    total_archivos = 0
    total_bytes = 0
    for zona in config.ZONAS_DATALAKE:
        carpeta = Path(config.ZONAS_DATALAKE[zona])
        # rglob incluye subcarpetas como curated/spark/
        archivos = sorted(carpeta.rglob("*.parquet")) if carpeta.exists() else []
        if not archivos:
            _log(f"  ⚠️ Zona '{zona}': sin archivos locales; se omite.")
            continue

        prefijo = "/".join(p for p in (config.S3_PREFIX, zona) if p)
        for archivo in archivos:
            relativo = archivo.relative_to(carpeta).as_posix()
            destino = f"{bucket}/{prefijo}/{relativo}"
            fs.put(str(archivo), destino)
            tamanio = archivo.stat().st_size
            total_archivos += 1
            total_bytes += tamanio
            _log(f"  ✅ {relativo} -> s3://{destino} ({tamanio / 1024:.1f} KB)")

    if total_archivos == 0:
        _log("\n⚠️ No había archivos locales para subir. Corre primero la Fase 6 en modo local:")
        _log("   python Mongo/scripts/data_lake_pipeline.py")
        return

    _log(f"\n✨ Migración finalizada: {total_archivos} archivo(s) | {total_bytes / (1024 * 1024):.2f} MB subidos.")
    _log("   Pon DATA_LAKE_BACKEND=s3 en el .env para que los pipelines usen la nube.")


if __name__ == "__main__":
    subir_data_lake()
