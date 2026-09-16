"""Entidad Reproducción (hecho transaccional: usuario ve una película)."""

import random

from faker import Faker

_fake = Faker("es_CO")

_DISPOSITIVOS = ["Smart TV", "Smartphone", "Tablet", "PC", "Consola"]
_CALIDADES = ["SD", "HD", "HD", "4K"]
_ESTADOS = ["Completada", "Completada", "Completada", "Interrumpida", "Pendiente"]


def generar(indice, usuarios_ids, peliculas, tarifa_por_minuto):
    """Construye el documento de una reproducción.

    - `peliculas`: documentos con `_id` y `duracion_min`.
    """
    pelicula = random.choice(peliculas)
    duracion = pelicula["duracion_min"]
    estado = random.choice(_ESTADOS)
    if estado == "Completada":
        minutos = duracion
    else:
        minutos = random.randint(5, max(6, duracion - 1))
    return {
        "codigo_reproduccion": f"REP-2026-{indice + 1:06d}",
        "usuario_id": random.choice(usuarios_ids),
        "pelicula_id": pelicula["_id"],
        "fecha_reproduccion": _fake.date_time_between(start_date="-1y", end_date="now"),
        "dispositivo": random.choice(_DISPOSITIVOS),
        "calidad": random.choice(_CALIDADES),
        "estado": estado,
        "minutos_visualizados": minutos,
        "progreso_pct": round(min(minutos / duracion * 100, 100), 1),
        "valor_estimado": round(minutos * tarifa_por_minuto, 2),
    }