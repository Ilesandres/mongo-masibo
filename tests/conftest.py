# -*- coding: utf-8 -*-
"""Configuración común de las pruebas (pytest) — Hyperflix.

Las pruebas NUNCA tocan servicios reales (MongoDB Atlas, S3, BigQuery):
  * se fuerzan ``DATA_LAKE_BACKEND=local`` y ``DW_BACKEND=none`` ANTES de
    importar ``config`` (``load_dotenv`` no pisa variables ya definidas, así
    que el ``.env`` real del laboratorio no afecta a las pruebas);
  * el Data Lake se redirige a una carpeta temporal (fixture ``lake_temporal``).

Así corren igual en el PC del estudiante y en GitHub Actions (CI/CD).
"""
import os
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]

# Entorno aislado (debe ir antes de cualquier "import config")
os.environ["DATA_LAKE_BACKEND"] = "local"
os.environ["DW_BACKEND"] = "none"

for carpeta in (RAIZ, RAIZ / "Mongo", RAIZ / "Mongo" / "scripts"):
    sys.path.insert(0, str(carpeta))

import pytest  # noqa: E402

import config  # noqa: E402


@pytest.fixture
def lake_temporal(tmp_path, monkeypatch):
    """Data Lake local en una carpeta temporal (no pisa ``Mongo/data_lake``)."""
    zonas = {zona: tmp_path / zona for zona in ("raw", "processed", "curated")}
    monkeypatch.setattr(config, "DATA_LAKE_BACKEND", "local")
    monkeypatch.setattr(config, "ZONAS_DATALAKE", zonas)
    return zonas
