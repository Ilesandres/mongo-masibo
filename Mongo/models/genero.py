"""Entidad Género (catálogo de géneros normalizado).

Se separa de la película para evitar repetir strings en todas las películas:
la película referencia su género por `genero_codigo`.
"""

GENEROS = [
    ("Acción", "Persecuciones, combates y secuencias de alta intensidad"),
    ("Comedia", "Situaciones humorísticas y entretenimiento ligero"),
    ("Drama", "Historias con profundidad emocional y conflicto"),
    ("Ciencia Ficción", "Futuros, tecnología y exploración espacial"),
    ("Terror", "Suspenso, miedo y sobrenatural"),
    ("Documental", "Contenido educativo y factual"),
    ("Romance", "Historias de amor y relaciones"),
    ("Animación", "Producciones animadas para toda la familia"),
]


def generar(indice):
    """Construye el documento de un género del catálogo."""
    nombre, descripcion = GENEROS[indice % len(GENEROS)]
    return {
        "codigo_genero": f"GEN-{indice + 1:03d}",
        "nombre": nombre,
        "descripcion": descripcion,
    }


def nombres():
    """Devuelve la lista de nombres de géneros (uso crítico/enriquecimiento)."""
    return [nombre for nombre, _ in GENEROS]