# -*- coding: utf-8 -*-
"""Decisiones de la capa de Data Warehouse en la nube (Mongo/dw_cloud.py), sin red."""
from types import SimpleNamespace

import pytest

import config
import dw_cloud


class ClienteFalso:
    """Imita bigquery.Client.get_dataset() con la política de expiración del dataset."""

    def __init__(self, expiracion_ms):
        self._dataset = SimpleNamespace(
            default_table_expiration_ms=expiracion_ms,
            default_partition_expiration_ms=expiracion_ms,
        )

    def get_dataset(self, _ref):
        return self._dataset


SANDBOX = ClienteFalso(5_184_000_000)  # 60 días: lo que impone BigQuery Sandbox
CON_FACTURACION = ClienteFalso(None)


@pytest.fixture
def bigquery(monkeypatch):
    monkeypatch.setattr(config, "DW_BACKEND", "bigquery")
    monkeypatch.setattr(config, "BQ_PROJECT", "proyecto-pruebas")
    monkeypatch.setattr(config, "BQ_DATASET", "hyperflix")


def test_capa_apagada_por_defecto():
    assert not dw_cloud.activo()
    assert "DW_BACKEND=none" in dw_cloud.apagado()


def test_tabla_id_bigquery(bigquery):
    assert dw_cloud.activo() and dw_cloud.es_bigquery()
    assert dw_cloud.tabla_id("fact_consumo") == "proyecto-pruebas.hyperflix.fact_consumo"


def test_detecta_sandbox(bigquery):
    assert dw_cloud.es_sandbox(SANDBOX)
    assert not dw_cloud.es_sandbox(CON_FACTURACION)


@pytest.mark.parametrize(
    "modo, cliente, campo_esperado",
    [
        ("auto", SANDBOX, None),                    # incidente Sesión 22: en sandbox → ingesta
        ("auto", CON_FACTURACION, "fecha_id"),
        ("ingesta", CON_FACTURACION, None),
        ("fecha", SANDBOX, "fecha_id"),
    ],
)
def test_resolver_particion(bigquery, monkeypatch, modo, cliente, campo_esperado):
    monkeypatch.setattr(config, "DW_PARTICION_MODO", modo)
    campo, descripcion = dw_cloud.resolver_particion(cliente)
    assert campo == campo_esperado
    assert descripcion
