# -*- coding: utf-8 -*-
"""Abstracción local ↔ S3 del Data Lake (Mongo/almacenamiento.py), sin red."""
import pandas as pd
import pytest

import almacenamiento
import config


@pytest.fixture
def backend_s3(monkeypatch):
    monkeypatch.setattr(config, "DATA_LAKE_BACKEND", "s3")
    monkeypatch.setattr(config, "S3_BUCKET", "bucket-pruebas")
    monkeypatch.setattr(config, "S3_PREFIX", "hyperflix")
    monkeypatch.setattr(config, "AWS_REGION", "us-east-2")
    monkeypatch.setattr(config, "S3_ENDPOINT_URL", "")


def test_ruta_local(lake_temporal):
    assert almacenamiento.backend() == "local"
    assert almacenamiento.ruta("raw", "usuarios") == str(lake_temporal["raw"] / "usuarios.parquet")


def test_ruta_s3_con_prefijo(backend_s3):
    assert almacenamiento.ruta("curated", "spark/evolucion_mensual") == (
        "s3://bucket-pruebas/hyperflix/curated/spark/evolucion_mensual.parquet"
    )


def test_s3_sin_bucket_falla_con_mensaje_claro(backend_s3, monkeypatch):
    monkeypatch.setattr(config, "S3_BUCKET", "")
    with pytest.raises(RuntimeError, match="S3_BUCKET"):
        almacenamiento._verificar_s3()


def test_s3_region_mal_escrita_se_detecta(backend_s3, monkeypatch):
    # Incidente real de la Sesión 20: "region=us-east-2" pegado en el .env
    monkeypatch.setattr(config, "AWS_REGION", "region=us-east-2")
    with pytest.raises(RuntimeError, match="no es una región válida"):
        almacenamiento._verificar_s3()


def test_storage_options_minio_usa_path_style(backend_s3, monkeypatch):
    monkeypatch.setattr(config, "S3_ENDPOINT_URL", "http://localhost:9000")
    opciones = almacenamiento.storage_options()
    assert opciones["endpoint_url"] == "http://localhost:9000"
    assert opciones["config_kwargs"] == {"s3": {"addressing_style": "path"}}


def test_roundtrip_parquet_local(lake_temporal):
    assert almacenamiento.crear_estructura() == "local"
    df = pd.DataFrame({"codigo": ["A", "B"], "valor": [1.5, 2.5]})
    almacenamiento.escribir_parquet(df, "processed", "prueba")
    pd.testing.assert_frame_equal(almacenamiento.leer_parquet("processed", "prueba"), df)

    total_archivos, total_bytes, por_zona = almacenamiento.inventario()
    assert total_archivos == 1 and total_bytes > 0
    assert por_zona["processed"][0] == 1
