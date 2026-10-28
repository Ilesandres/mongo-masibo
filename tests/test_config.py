# -*- coding: utf-8 -*-
"""Coherencia de las constantes centralizadas en config.py."""
import config


def test_entero_convierte_y_tolera_basura():
    assert config._entero("42", 0) == 42
    assert config._entero(None, 7) == 7
    assert config._entero("no-es-numero", 3) == 3


def test_indices_unicos_apuntan_a_colecciones_oltp():
    assert set(config.UNIQUE_INDEXES) <= set(config.COLECCIONES_OLTP)
    assert set(config.INDEXES_OLTP) <= set(config.COLECCIONES_OLTP)


def test_data_lake_incluye_oltp_y_vista_olap():
    assert config.COLECCION_OLAP in config.COLECCIONES_DATALAKE
    assert set(config.COLECCIONES_OLTP) <= set(config.COLECCIONES_DATALAKE)


def test_dw_nube_usa_las_mismas_tablas_que_la_fase_9():
    assert sorted(config.TABLAS_DW_NUBE.values()) == sorted(config.COLECCIONES_DW)


def test_umbrales_de_segmentacion_ordenados():
    assert config.SEGMENTO_COMPLETO_MIN > config.SEGMENTO_PARCIAL_MIN > 0
    assert config.SEGMENTO_VIP_MIN > config.SEGMENTO_PREMIUM_MIN > config.SEGMENTO_FRECUENTE_MIN


def test_nombres_de_indices_olap_unicos():
    nombres = [nombre for nombre, _ in config.INDEXES_OLAP]
    assert len(nombres) == len(set(nombres))


def test_pruebas_corren_aisladas_de_la_nube():
    # conftest.py fuerza el entorno local: ninguna prueba debe hablar con S3/BigQuery
    assert config.DATA_LAKE_BACKEND == "local"
    assert config.DW_BACKEND == "none"
