"""Entidades normalizadas del dominio Hyperflix.

Cada entidad vive en su propio módulo y expone una función `generar(indice, ...)`
que construye el documento MongoDB correspondiente. Centralizar aquí el origen de
los datos permite separar la definición (modelo) de la orquestación (scripts).
"""

from . import (
    director,
    genero,
    pago,
    pelicula,
    plan,
    reproduccion,
    resena,
    suscripcion,
    usuario,
)

__all__ = [
    "director",
    "genero",
    "pago",
    "pelicula",
    "plan",
    "reproduccion",
    "resena",
    "suscripcion",
    "usuario",
]