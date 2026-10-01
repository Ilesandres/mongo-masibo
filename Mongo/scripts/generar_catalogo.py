"""
generar_catalogo.py — Gobierno de Datos y Catálogo Automatizado (Hyperflix).

Inspired en la guía académica: en una arquitectura de datos moderna el
"Data Discovery" es tan crítico como el almacenamiento. Este script INSPECCIONA
la base de datos real (no inventa nada), aplana los documentos anidados, detecta
los índices y exporta un catálogo de datos profesional en Excel.

Genera 2 pestañas:
  1. "Resumen Arquitectónico": inventario de colecciones clasificadas por su rol
     (OLTP, OLAP, Data Warehouse) con volumen real de documentos.
  2. "Diccionario de Datos": campo (incluidos anidados como `generos[0].codigo_genero`),
     tipo de dato estandarizado, PK/FK, si está indexado y descripción de negocio.

Ejecutar:  python Mongo/scripts/generar_catalogo.py
"""
import sys
from datetime import datetime
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # raíz (config)
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # Mongo/ (conexion)

import config
from conexion import conectar_mongodb

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

# ── Metadatos de negocio (contexto Hyperflix) ────────────────
# Rol de cada colección dentro de la arquitectura.
ROL_COLECCION = {
    "generos": ("OLTP", "Catálogo maestro de géneros (dimensión de baja cardinalidad)."),
    "directores": ("OLTP", "Catálogo maestro de directores (dimensión)."),
    "planes": ("OLTP", "Catálogo de planes de suscripción (producto)."),
    "usuarios": ("OLTP", "Entidad central de clientes; fuente para la dimensión cliente."),
    "peliculas": ("OLTP", "Catálogo de títulos disponibles en streaming."),
    "suscripciones": ("OLTP", "Suscripciones activas/inactivas de los usuarios a un plan."),
    "pagos": ("OLTP", "Transacciones de cobro de suscripciones (ingresos)."),
    "resenas": ("OLTP", "Valoraciones de usuarios sobre películas."),
    "reproducciones": ("OLTP", "Hecho de consumo: cada reproducción es un evento de viewing."),
    "reproducciones_analiticas": ("OLAP", "Hechos analíticos desnormalizados para agregaciones."),
    "dim_tiempo": ("Data Warehouse", "Dimensión temporal (año/mes/día) para el modelo estrella."),
    "dim_cliente": ("Data Warehouse", "Dimensión cliente (segmento, ciudad, plan)."),
    "dim_pelicula": ("Data Warehouse", "Dimensión película (género, director, duración)."),
    "fact_consumo": ("Data Warehouse", "Tabla de hechos de consumo (métrica, fecha, cliente, película)."),
}

# Descripciones de negocio por campo (las más relevantes; el resto se describe por rol).
DESCRIPCIONES = {
    "_id": "Identificador único interno (ObjectId generado por MongoDB).",
    "codigo_genero": "Clave natural del género (PK de negocio).",
    "nombre_genero": "Nombre del género cinematográfico.",
    "codigo_director": "Clave natural del director (PK de negocio).",
    "nombre_director": "Nombre completo del director.",
    "codigo_plan": "Clave natural del plan de suscripción (PK de negocio).",
    "nombre_plan": "Nombre comercial del plan.",
    "precio_mensual": "Precio mensual del plan en moneda local.",
    "codigo_usuario": "Clave natural del usuario (código de negocio).",
    "email": "Correo único del usuario; identifica al cliente (índice único).",
    "nombre": "Nombre del usuario.",
    "apellido": "Apellido del usuario.",
    "fecha_nacimiento": "Fecha de nacimiento del usuario.",
    "genero_usuario": "Género del usuario.",
    "pais": "País de residencia del usuario.",
    "ciudad": "Ciudad del usuario (segmentación geográfica).",
    "direccion": "Objeto anidado con la dirección completa del usuario.",
    "codigo_pelicula": "Clave natural de la película (PK de negocio).",
    "titulo": "Título de la película.",
    "anio_estreno": "Año de estreno de la película.",
    "genero": "Género(s) de la película; puede ser arreglo de códigos de género.",
    "director": "Director(es) de la película; arreglo de códigos de director.",
    "duracion_min": "Duración de la película en minutos.",
    "clasificacion": "Clasificación por edad (TP, 7+, 13+, 16+).",
    "codigo_suscripcion": "Clave natural de la suscripción (PK de negocio).",
    "usuario_id": "Referencia al usuario propietario de la suscripción (FK).",
    "plan_codigo": "Referencia al plan contratado (FK).",
    "fecha_inicio": "Fecha de inicio de la suscripción.",
    "fecha_fin": "Fecha de finalización de la suscripción.",
    "estado": "Estado de la suscripción (activa/cancelada/pausada).",
    "codigo_pago": "Clave natural del pago (PK de negocio).",
    "suscripcion_id": "Referencia a la suscripción facturada (FK).",
    "monto": "Monto del pago.",
    "fecha_pago": "Fecha de registro del pago.",
    "metodo_pago": "Método de pago utilizado.",
    "codigo_resena": "Clave natural de la reseña (PK de negocio).",
    "pelicula_id": "Referencia a la película reseñada (FK).",
    "puntuacion": "Puntuación dada por el usuario (1-5).",
    "comentario": "Comentario de la reseña.",
    "fecha_resena": "Fecha de la reseña.",
    "codigo_reproduccion": "Clave natural del evento de reproducción (PK de negocio).",
    "fecha_reproduccion": "Fecha/hora de la reproducción (eje temporal del hecho).",
    "minutos_reproducidos": "Minutos reproducidos en la sesión.",
    "dispositivo": "Dispositivo de reproducción (TV, móvil, tablet, PC).",
    "completada": "Indica si la reproducción se completó al 100%.",
    "anio": "Año de la reproducción (columna derivada para agregaciones).",
    "mes": "Mes de la reproducción (columna derivada).",
    "dia": "Día de la reproducción (columna derivada).",
    "valor_estimado": "Valor estimado de la reproducción para analítica.",
}

# Tipos de Python/BSON → tipo de dato estandarizado del diccionario.
TIPOS = {
    str: "String",
    int: "Integer",
    float: "Double",
    bool: "Boolean",
    dict: "Object",
    list: "Array",
    type(None): "Null",
}


def tipo_dato(valor):
    if type(valor).__name__ in ("ObjectId", "Decimal128", "Int64"):
        return {"ObjectId": "ObjectId", "Decimal128": "Decimal", "Int64": "Integer"}[type(valor).__name__]
    if isinstance(valor, datetime):
        return "Timestamp"
    return TIPOS.get(type(valor), type(valor).__name__)


def aplanar(documento, prefijo=""):
    """Aplana un documento anidido -> (ruta_campo, tipo, valor_ejemplo)."""
    for clave, valor in documento.items():
        ruta = f"{prefijo}.{clave}" if prefijo else clave
        if isinstance(valor, dict):
            if valor:
                yield from aplanar(valor, ruta)
            else:
                yield ruta, "Object", "{}"
        elif isinstance(valor, list) and valor and all(isinstance(v, dict) for v in valor):
            # Arreglo de objetos embebidos: se usa el primer elemento como muestra.
            yield from aplanar(valor[0], f"{ruta}[0]")
        else:
            yield ruta, tipo_dato(valor), valor


def campos_indexados(coleccion):
    """Devuelve el conjunto de campos cubiertos por algún índice de la colección."""
    indexados = set()
    for idx in coleccion.index_information().values():
        for campo in idx.get("key", []):
            indexados.add(campo)
    return indexados


def rol_coleccion(nombre):
    if nombre in ROL_COLECCION:
        return ROL_COLECCION[nombre]
    if nombre == config.COLECCION_OLAP:
        return ("OLAP", "Colección analítica (agregaciones y benchmarks).")
    return ("No clasificada", "Colección no contemplada en el modelo de referencia.")


def todas_las_colecciones(db):
    existentes = set(db.list_collection_names())
    catalogadas = (
        set(config.COLECCIONES_OLTP)
        | {config.COLECCION_OLAP}
        | set(config.COLECCIONES_DW)
    )
    # Las que existen en la BD primero (fuente de verdad), luego las del modelo.
    return [c for c in sorted(existentes) if c != "system.views"] + sorted(catalogadas - existentes)


def clave_de(campo, coleccion):
    """Determina PK / FK de un campo según el modelo Hyperflix."""
    base = campo.split(".")[-1].split("[")[0]
    if campo == "_id":
        return "PK (ObjectId)"
    if base == config.UNIQUE_INDEXES.get(coleccion):
        return "PK (clave natural)"
    if base.endswith("_id") and base not in ("usuario_id", "pelicula_id", "suscripcion_id"):
        return "FK"
    if base.endswith("_id"):
        return "FK"
    if base in ("genero", "director", "plan") and campo != "_id":
        return "FK"
    return "—"


def descripcion_de(campo, coleccion):
    base = campo.split(".")[-1].split("[")[0]
    if base in DESCRIPCIONES:
        return DESCRIPCIONES[base]
    if base == "usuario":
        return "Objeto anidado con datos del usuario embebidos (desnormalización)."
    if base == "pelicula":
        return "Objeto anidido con datos de la película embebidos (desnormalización)."
    return "Campo de la colección (ver diccionario)."


def construir_filas_diccionario(db, coleccion_nombre):
    coleccion = db[coleccion_nombre]
    doc = coleccion.find_one()
    if not doc:
        return []
    indexados = campos_indexados(coleccion)
    filas = []
    for campo, tipo, ejemplo in aplanar(doc):
        indexado = "Sí" if campo in indexados or campo.split(".")[-1].split("[")[0] in indexados else "No"
        filas.append(
            {
                "coleccion": coleccion_nombre,
                "campo": campo,
                "tipo": tipo,
                "clave": clave_de(campo, coleccion_nombre),
                "indexado": indexado,
                "descripcion": descripcion_de(campo, coleccion_nombre),
                "ejemplo": str(ejemplo)[:40],
            }
        )
    return filas


def main():
    client, db = conectar_mongodb()
    if not client:
        print("❌ No se pudo conectar. Revisa MONGO_URI en .env.")
        sys.exit(1)

    print(f"\n📊 Generando catálogo de datos para: {config.DB_NAME}\n")

    # ── Datos: resumen arquitectónico + diccionario ──
    resumen, diccionario = [], []
    for nombre in todas_las_colecciones(db):
        coleccion = db[nombre]
        docs = coleccion.estimated_document_count()
        try:
            tamano_kb = round(coleccion.database.client[f"{config.DB_NAME}"].command("collstats", nombre)["size"] / 1024, 2)
        except Exception:
            tamano_kb = 0
        rol, desc = rol_coleccion(nombre)
        num_indices = len(list(coleccion.list_indexes()))
        resumen.append(
            {
                "coleccion": nombre,
                "rol": rol,
                "documentos": docs,
                "tamano_kb": tamano_kb,
                "indices": num_indices,
                "descripcion": desc,
            }
        )
        filas = construir_filas_diccionario(db, nombre)
        diccionario.extend(filas)
        print(f"  ✅ {nombre:28} rol={rol:16} docs={docs}")

    # ── Excel ──
    wb = Workbook()

    # Pestaña 1: Resumen Arquitectónico
    ws1 = wb.active
    ws1.title = "Resumen Arquitectónico"
    cab1 = ["Colección", "Capa / Rol", "Documentos", "Tamaño (KB)", "Índices", "Descripción"]
    ws1.append(cab1)
    for fila in resumen:
        ws1.append([fila["coleccion"], fila["rol"], fila["documentos"], fila["tamano_kb"], fila["indices"], fila["descripcion"]])

    # Pestaña 2: Diccionario de Datos
    ws2 = wb.create_sheet("Diccionario de Datos")
    cab2 = ["Colección", "Campo", "Tipo de dato", "Clave (PK/FK)", "¿Indexado?", "Descripción de negocio", "Ejemplo"]
    ws2.append(cab2)
    for fila in diccionario:
        ws2.append([fila["coleccion"], fila["campo"], fila["tipo"], fila["clave"], fila["indexado"], fila["descripcion"], fila["ejemplo"]])

    # Estilos (encabezado azul, freezing, autofiltro, anchos).
    header_fill = PatternFill("solid", fgColor="1F4E78")
    header_font = Font(bold=True, color="FFFFFF")
    for ws in (ws1, ws2):
        for celda in ws[1]:
            celda.fill = header_fill
            celda.font = header_font
            celda.alignment = Alignment(horizontal="center", vertical="center")
        ws.freeze_panes = "A2"
        ws.auto_filter.ref = ws.dimensions

    # Resaltar indexado=Sí y PK en el diccionario.
    verde = PatternFill("solid", fgColor="C6EFCE")
    for fila in ws2.iter_rows(min_row=2):
        if fila[4].value == "Sí":
            fila[4].fill = verde
        if str(fila[3].value).startswith("PK"):
            fila[3].font = Font(bold=True)

    anchos = {ws1: [26, 18, 12, 14, 10, 60], ws2: [24, 34, 14, 16, 12, 55, 24]}
    for ws, medidas in anchos.items():
        for i, ancho in enumerate(medidas, start=1):
            ws.column_dimensions[get_column_letter(i)].width = ancho

    # ── Guardar ──
    fecha = datetime.now().strftime("%Y%m%d")
    carpeta = Path(__file__).resolve().parents[1] / "catalogo_datos"
    carpeta.mkdir(exist_ok=True)
    archivo = carpeta / f"Catalogo_Datos_{config.DB_NAME}_{fecha}.xlsx"
    wb.save(archivo)

    print(f"\n📄 Catálogo guardado en: {archivo}")
    print(f"   Resumen: {len(resumen)} colecciones | Diccionario: {len(diccionario)} campos")
    print("\n🎉 ¡Catálogo de datos generado con éxito!")

    client.close()
    print("🔒 Conexión cerrada.")


if __name__ == "__main__":
    main()
