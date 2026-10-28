# -*- coding: utf-8 -*-
"""Reglas de negocio de las entidades normalizadas (Mongo/models/)."""
import random

import pytest

import config
from models import director, genero, pelicula, plan, reproduccion, usuario


@pytest.fixture(autouse=True)
def semilla():
    random.seed(1234)


def test_codigos_deterministas_por_indice():
    assert usuario.generar(0)["codigo_usuario"] == "USU00001"
    assert genero.generar(0)["codigo_genero"] == "GEN-001"
    assert director.generar(9)["codigo_director"] == "DIR-010"


def test_emails_de_usuario_unicos():
    emails = {usuario.generar(i)["email"] for i in range(200)}
    assert len(emails) == 200


def test_planes_por_codigo_coincide_con_generar():
    catalogo = plan.por_codigo()
    for i in range(len(catalogo)):
        documento = plan.generar(i)
        assert catalogo[documento["codigo_plan"]]["precio_mensual"] == documento["precio_mensual"]


def test_pelicula_referencia_catalogos_normalizados():
    documento = pelicula.generar(0, ["GEN-001"], ["DIR-001"])
    assert documento["genero_codigo"] == "GEN-001"
    assert documento["director_codigo"] == "DIR-001"
    assert 75 <= documento["duracion_min"] <= 180


def test_reproduccion_respeta_reglas_de_negocio():
    peliculas = [{"_id": f"p{i}", "duracion_min": 90 + i} for i in range(5)]
    for i in range(300):
        doc = reproduccion.generar(i, ["u1", "u2"], peliculas, config.TARIFA_POR_MINUTO)
        duracion = next(p["duracion_min"] for p in peliculas if p["_id"] == doc["pelicula_id"])
        assert 0 < doc["progreso_pct"] <= 100
        assert doc["valor_estimado"] == round(doc["minutos_visualizados"] * config.TARIFA_POR_MINUTO, 2)
        if doc["estado"] == "Completada":
            assert doc["minutos_visualizados"] == duracion
        else:
            assert doc["minutos_visualizados"] < duracion
