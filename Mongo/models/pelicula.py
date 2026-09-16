"""Entidad Película (catálogo de contenido).

Normalizada: referencia a `genero_codigo` y `director_codigo` en lugar de
repetir strings. La desnormalización (nombres) se resuelve en la zona PROCESSED
del data lake y en la vista OLAP.
"""

import random

from faker import Faker

_fake = Faker("es_CO")


def generar(indice, generos_codigos, directores_codigos):
    """Construye el documento de una película del catálogo."""
    anio = random.randint(1990, 2026)
    return {
        "codigo_pelicula": f"PEL{indice + 1:05d}",
        "titulo": f"{_fake.word().capitalize()} {_fake.word().capitalize()}",
        "genero_codigo": random.choice(generos_codigos),
        "director_codigo": random.choice(directores_codigos),
        "anio": anio,
        "duracion_min": random.randint(75, 180),
        "fecha_estreno": _fake.date_time_between(
            start_date=f"-{2026 - anio}y", end_date="now"
        ),
    }