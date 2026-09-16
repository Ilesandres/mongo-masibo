"""Entidad Plan (planes de suscripción de Hyperflix)."""

PLANES = [
    ("PLA-001", "Básico", 15_000, "SD", 1),
    ("PLA-002", "Estándar", 30_000, "HD", 2),
    ("PLA-003", "Premium", 45_000, "4K", 4),
]


def generar(indice):
    """Construye el documento de un plan de suscripción."""
    codigo, nombre, precio, calidad_max, pantallas = PLANES[indice % len(PLANES)]
    return {
        "codigo_plan": codigo,
        "nombre": nombre,
        "precio_mensual": precio,
        "calidad_maxima": calidad_max,
        "pantallas_simultaneas": pantallas,
        "activo": True,
    }


def por_codigo():
    """Devuelve un dict {codigo_plan: {"nombre", "precio_mensual"}} para enriquecimiento."""
    return {
        codigo: {"nombre": nombre, "precio_mensual": precio}
        for codigo, nombre, precio, _, _ in PLANES
    }