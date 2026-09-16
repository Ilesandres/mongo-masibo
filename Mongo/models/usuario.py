"""Entidad Usuario (suscriptor de Hyperflix)."""

from faker import Faker

_fake = Faker("es_CO")


def generar(indice, plan="Básico"):
    """Construye el documento de un usuario de Hyperflix."""
    return {
        "codigo_usuario": f"USU{indice + 1:05d}",
        "nombre": _fake.name(),
        "email": f"usuario{indice + 1}@hyperflix.local",
        "telefono": _fake.phone_number(),
        "direccion": {
            "calle": _fake.street_address(),
            "ciudad": _fake.city(),
            "pais": "Colombia",
        },
        "fecha_registro": _fake.date_time_between(start_date="-2y", end_date="now"),
        "activo": bool((indice % 5) != 4),
        "plan": plan,
    }