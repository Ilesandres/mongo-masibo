"""Entidad Reseña (valoración de un usuario sobre una película)."""

import random

from faker import Faker

_fake = Faker("es_CO")

_COMENTARIOS = [
    "Excelente, la recomiendo",
    "Muy buena historia",
    "Entretenida pero predecible",
    "Buena fotografía",
    "Me gustó el final",
    "Podría ser mejor",
    "No era lo que esperaba",
    "Gran actuación",
]


def generar(indice, usuarios_ids, peliculas_ids):
    """Construye el documento de una reseña."""
    return {
        "codigo_resena": f"RES{indice + 1:07d}",
        "usuario_id": random.choice(usuarios_ids),
        "pelicula_id": random.choice(peliculas_ids),
        "puntuacion": random.randint(1, 5),
        "comentario": random.choice(_COMENTARIOS),
        "fecha_resena": _fake.date_time_between(start_date="-1y", end_date="now"),
    }