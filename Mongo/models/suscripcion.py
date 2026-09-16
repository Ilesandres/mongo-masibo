"""Entidad Suscripción (relación Usuario <-> Plan).

Registra el contrato entre un usuario y un plan: fecha de inicio, estado
de la suscripción y renovación automática.
"""

import random

from faker import Faker

_fake = Faker("es_CO")

_ESTADOS = ["Activa", "Activa", "Activa", "Cancelada", "Vencida"]


def generar(indice, usuarios, planes):
    """Construye el documento de una suscripción.

    - `usuarios`: documentos de usuario con `_id` y `fecha_registro`.
    - `planes`: documentos de plan con `codigo_plan`.
    """
    usuario = random.choice(usuarios)
    plan = random.choice(planes)
    return {
        "codigo_suscripcion": f"SUS{indice + 1:06d}",
        "usuario_id": usuario["_id"],
        "codigo_plan": plan["codigo_plan"],
        "fecha_inicio": _fake.date_time_between(
            start_date=usuario["fecha_registro"], end_date="now"
        ),
        "estado": random.choice(_ESTADOS),
        "renovacion_automatica": random.choice([True, True, False]),
    }