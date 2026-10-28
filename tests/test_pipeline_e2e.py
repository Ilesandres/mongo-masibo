# -*- coding: utf-8 -*-
"""Prueba de humo de punta a punta (sin MongoDB ni nube).

Genera un Data Lake sintético MINÚSCULO en una carpeta temporal
(RAW → PROCESSED → CURATED) y verifica que el ETL de la Fase 10 lo transforma
al esquema estrella del DW (dim_tiempo, dim_cliente, dim_pelicula, fact_consumo).
"""
import random

import pytest

import config

REPRODUCCIONES = 300
USUARIOS = 40
PELICULAS = 25


@pytest.fixture
def lake_generado(lake_temporal):
    import data_lake_pipeline as pipeline
    import generar_data_lake_sintetico as generador

    random.seed(42)
    generador.crear_estructura()
    generador.generar_raw(
        num_usuarios=USUARIOS,
        num_peliculas=PELICULAS,
        num_suscripciones=30,
        num_pagos=60,
        num_resenas=50,
        num_reproducciones=REPRODUCCIONES,
        tamano_lote=100,
    )
    generador.procesar_reproducciones(100)
    pipeline.procesar_catalogos()
    generador.generar_curated(100)
    return lake_temporal


def test_zonas_del_lake_generadas(lake_generado):
    for zona in ("raw", "processed", "curated"):
        assert list(lake_generado[zona].glob("*.parquet")), f"zona {zona} vacía"
    for nombre in ("fact_reproduccion", "dim_usuario", "dim_pelicula", "dim_fecha"):
        assert (lake_generado["curated"] / f"{nombre}.parquet").exists()


def test_etl_curated_a_data_warehouse(lake_generado):
    import almacenamiento
    import data_warehouse_cloud as etl

    tablas = etl.preparar_tablas()
    assert set(tablas) == set(config.COLECCIONES_DW)

    # El hecho solo guarda reproducciones COMPLETADAS (regla de la zona PROCESSED)
    hechos_lake = len(almacenamiento.leer_parquet("curated", "fact_reproduccion"))
    assert 0 < hechos_lake <= REPRODUCCIONES

    fact = tablas["fact_consumo"]
    assert len(fact) == hechos_lake
    assert set(fact["estado"]) == {"Completada"}
    assert list(fact.columns) == etl.COLUMNAS_FACT
    assert fact["fecha_id"].notna().all()
    assert fact["codigo_reproduccion"].is_unique

    assert set(tablas["dim_tiempo"]["fin_semana"]) <= {"Sí", "No"}
    assert tablas["dim_cliente"]["reproducciones"].sum() == hechos_lake
    assert tablas["dim_pelicula"]["reproducciones"].sum() == hechos_lake

    # --limite recorta solo el hecho
    assert len(etl.preparar_tablas(limite=50)["fact_consumo"]) == 50
