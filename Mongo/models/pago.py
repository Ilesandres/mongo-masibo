"""Entidad Pago (cobros asociados a una suscripción)."""

import random
from datetime import datetime, timedelta

from faker import Faker

_fake = Faker("es_CO")

_METODOS = ["Tarjeta", "PayPal", "PSE", "Nequi"]
_ESTADOS = ["Aprobado", "Aprobado", "Aprobado", "Rechazado", "Reembolsado"]


def generar(indice, suscripciones):
    """Construye el documento de un pago.

    - `suscripciones`: documentos de suscripción enriquecidos con `_id`,
      `precio_mensual` y `fecha_inicio`.
    """
    suscripcion = random.choice(suscripciones)
    inicio = suscripcion["fecha_inicio"]
    limite = max(inicio, datetime.now() - timedelta(days=365))
    return {
        "codigo_pago": f"PAG{indice + 1:07d}",
        "suscripcion_id": suscripcion["_id"],
        "fecha_pago": _fake.date_time_between(start_date=limite, end_date="now"),
        "monto": suscripcion["precio_mensual"],
        "metodo_pago": random.choice(_METODOS),
        "estado": random.choice(_ESTADOS),
    }