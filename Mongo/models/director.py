"""Entidad Director (catálogo de directores normalizado).

Cada película referencia a un director por `director_codigo`, evitando
repetir el nombre del director en cada documento de película.
"""

from faker import Faker

_fake = Faker("es_CO")


def generar(indice):
    """Construye el documento de un director del catálogo."""
    return {
        "codigo_director": f"DIR-{indice + 1:03d}",
        "nombre": _fake.name(),
        "nacionalidad": _fake.country(),
    }