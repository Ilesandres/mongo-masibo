"""Streaming (simulación de Kafka Consumer) — Terminal 1.

Escucha en tiempo real la colección `reproducciones` mediante MongoDB
Change Streams (patrón Change Data Capture). Agrupa el ciclo de vida de
cada reproducción (INSERT Pendiente -> UPDATE final) en una tarjeta
legible con barra de progreso, y al terminar muestra un resumen de la
sesión con la regla de negocio de streaming: reproducción de película
larga completada en una sola sesión (maratón).

Equivalencia con el laboratorio:
    MongoDB Change Streams  -> Kafka (producción)
    Python                  -> Spark Streaming (producción)
    db.reproducciones.watch -> Kafka Consumer
    for change in stream    -> procesamiento continuo
    tarjeta + alerta        -> dashboard / BI

Si el cluster no soporta Change Streams (p. ej. Atlas M0/M2), el script
detecta el error y cae a un modo fallback de polling (degradado).

Cómo usarlo (2 terminales):
    Terminal 1 (esta):  python Mongo/scripts/streaming.py
    Terminal 2:         python Mongo/scripts/generar_reproducciones_streaming.py
"""

import re
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # raíz (config)

if sys.platform == "win32":
    import ctypes

    kernel32 = ctypes.windll.kernel32
    kernel32.SetConsoleMode(kernel32.GetStdHandle(-11), 7)  # habilitar colores ANSI

import pymongo
from bson import ObjectId
from pymongo.errors import OperationFailure

import config

# ── Colores ANSI ─────────────────────────────────────
_GRIS = "\033[90m"
_AZUL = "\033[94m"
_VERDE = "\033[92m"
_AMARILLO = "\033[93m"
_ROJO = "\033[91m"
_MAGENTA = "\033[95m"
_CIAN = "\033[96m"
_RESET = "\033[0m"
_ANSI = re.compile(r"\x1b\[[0-9;]*m")


def _color(texto, codigo=_GRIS):
    return f"{codigo}{texto}{_RESET}"


def _padvis(texto, ancho, izquierda=True):
    """Rellena al ancho contando solo el texto visible (sin códigos ANSI)."""
    faltante = max(0, ancho - len(_ANSI.sub("", texto)))
    return (texto + " " * faltante) if izquierda else (" " * faltante + texto)


def _barra(progreso, ancho=20):
    pct = max(0.0, min(100.0, progreso or 0))
    relleno = round(pct / 100 * ancho)
    color = _VERDE if pct >= 100 else (_AMARILLO if pct >= 50 else _ROJO)
    return _color("█" * relleno + "░" * (ancho - relleno), color)


def _insignia(estado):
    if estado == "Completada":
        return _color("✅ COMPLETADA", _VERDE)
    if estado == "Interrumpida":
        return _color("⏹️  INTERRUMPIDA", _AMARILLO)
    if estado == "Pendiente":
        return _color("⏳ PENDIENTE", _CIAN)
    return _color(str(estado), _GRIS)


# ── Estado y estadísticas de la sesión ───────────────
activos = {}          # codigo -> último documento conocido
ids = {}              # _id -> codigo (para resolver DELETEs)
ESTADISTICAS = {
    "procesadas": 0,
    "completadas": 0,
    "interrumpidas": 0,
    "eliminadas": 0,
    "maratones": 0,
}


def _info_usuario(db, usuario_id):
    if not usuario_id:
        return "?"
    if isinstance(usuario_id, str):
        try:
            usuario_id = ObjectId(usuario_id)
        except Exception:
            return "?"
    doc = db.usuarios.find_one({"_id": usuario_id}, {"nombre": 1})
    return doc["nombre"] if doc else "?"


def _info_pelicula(db, pelicula_id):
    if not pelicula_id:
        return None
    if isinstance(pelicula_id, str):
        try:
            pelicula_id = ObjectId(pelicula_id)
        except Exception:
            return None
    return db.peliculas.find_one({"_id": pelicula_id}, {"titulo": 1, "duracion_min": 1})


def _registrar_doc(db, documento, refresco=True):
    """Guarda el último estado conocido de una reproducción en memoria."""
    codigo = documento.get("codigo_reproduccion")
    if not codigo:
        return
    if _id := documento.get("_id"):
        ids[_id] = codigo
    if not refresco and codigo in activos:
        if activos[codigo].get("estado") == documento.get("estado"):
            return  # sin novedad: no reinicia el reloj del flush
    documento["_ultima"] = datetime.now()
    activos[codigo] = documento


def _registrar_delete(change):
    doc_key = change.get("documentKey") or {}
    _id = doc_key.get("_id")
    codigo = ids.pop(_id, None)
    if codigo:
        activos.pop(codigo, None)
    ESTADISTICAS["eliminadas"] += 1
    hora = datetime.now().strftime("%H:%M:%S")
    print(_color(f"[{hora}] 🗑️  REP {codigo or _id} ELIMINADA — auditoría", _ROJO))
    print("-" * 66)


def _mostrar_tarjeta(db, documento):
    codigo = documento.get("codigo_reproduccion", "?")
    estado = documento.get("estado", "?")
    minutos = documento.get("minutos_visualizados") or 0
    pct = float(documento.get("progreso_pct") or 0)
    dispositivo = documento.get("dispositivo", "?")
    calidad = documento.get("calidad", "?")
    titulo, duracion = "?", 0
    pelicula = _info_pelicula(db, documento.get("pelicula_id"))
    if pelicula:
        titulo = pelicula.get("titulo", "?")
        duracion = pelicula.get("duracion_min") or 0
    usuario = _info_usuario(db, documento.get("usuario_id"))

    # estadísticas de la sesión
    ESTADISTICAS["procesadas"] += 1
    es_maraton = estado == "Completada" and (duracion or minutos) >= config.MINUTOS_MARATON
    if estado == "Completada":
        ESTADISTICAS["completadas"] += 1
        if es_maraton:
            ESTADISTICAS["maratones"] += 1
    elif estado == "Interrumpida":
        ESTADISTICAS["interrumpidas"] += 1

    ancho = 64
    filas = [
        _color(f"🎞️  REP {codigo}", _MAGENTA),
        "🎬  " + titulo,
        _color("👤  " + usuario, _GRIS),
        _color("📺  " + f"{dispositivo} · {calidad}", _GRIS),
        _insignia(estado) + f"  ·  {minutos} min · {pct:.0f}%",
        _barra(pct) + f"  {pct:.0f}%",
    ]
    if es_maraton:
        filas.append(
            _color(f"🚨 PELÍCULA LARGA COMPLETADA EN UNA SOLA SESIÓN (≥ {config.MINUTOS_MARATON} min)", _ROJO)
        )

    print(_color("┌" + "─" * ancho + "┐", _GRIS))
    for fila in filas:
        print(_color("│", _GRIS) + " " + _padvis(fila, ancho - 2) + " " + _color("│", _GRIS))
    print(_color("└" + "─" * ancho + "┘", _GRIS))
    print("-" * 66)


def flush_tarjetas(db):
    """Publica las reproducciones que ya no recibieron novedades (finalizada su escritura)."""
    ahora = datetime.now()
    vencidos = [
        codigo
        for codigo, doc in activos.items()
        if (ahora - doc.get("_ultima", ahora)).total_seconds() >= 1.3
    ]
    for codigo in vencidos:
        _mostrar_tarjeta(db, activos.pop(codigo))


def _procesar_change(db, change):
    op = change.get("operationType")
    if op in ("insert", "update"):
        doc = change.get("fullDocument")
        if doc:
            _registrar_doc(db, doc, refresco=True)
    elif op == "delete":
        _registrar_delete(change)


def _modo_fallback_polling(client, db):
    """Modo degradado para clusters sin Change Streams (Atlas M0/M2)."""
    print("🟡 Este cluster NO soporta Change Streams (típico de Atlas M0/M2).")
    print("   Cambio a modo fallback: polling de novedades cada 1,2 s (sin evento DELETE).\n")
    try:
        while True:
            ventana = datetime.now() - timedelta(seconds=8)
            documentos = list(
                db.reproducciones.find({"fecha_reproduccion": {"$gte": ventana}}).limit(200)
            )
            for doc in documentos:
                _registrar_doc(db, doc, refresco=False)
            flush_tarjetas(db)
            time.sleep(1.2)
    except KeyboardInterrupt:
        _resumen()


def _resumen():
    print()
    print(_color("═" * 66, _CIAN))
    print(_color("  📊 RESUMEN DE LA SESIÓN DE STREAMING", _CIAN))
    print(_color("═" * 66, _CIAN))
    filas = [
        ("🎞️  Reproducciones procesadas", ESTADISTICAS["procesadas"]),
        ("✅  Completadas", ESTADISTICAS["completadas"]),
        ("⏹️  Interrumpidas", ESTADISTICAS["interrumpidas"]),
        ("🗑️  Eliminadas (auditoría)", ESTADISTICAS["eliminadas"]),
        ("🚨  Maratones (≥ 120 min)", ESTADISTICAS["maratones"]),
    ]
    for etiqueta, valor in filas:
        print("  " + _padvis(_color(etiqueta, _AZUL) + f"{valor:>6}", 58))
    print(_color("═" * 66, _CIAN))


def simular_streaming_kafka():
    print("🔵 Iniciando pipeline de streaming (MongoDB Change Streams) — simula Kafka Consumer...\n")
    client = None
    try:
        client = pymongo.MongoClient(config.MONGO_URI, serverSelectionTimeoutMS=8000)
        client.admin.command("ping")
        db = client[config.DB_NAME]
        print(f"👂 Escuchando cambios en la colección '{config.DB_NAME}.reproducciones'...")
        print("   Deja esta terminal abierta; presiona Ctrl+C al final para ver el resumen.\n")
        print("   ▶ Terminal 2:  python Mongo/scripts/generar_reproducciones_streaming.py\n")
        print("-" * 66)

        try:
            with db.reproducciones.watch(full_document="updateLookup") as stream:
                while stream.alive:
                    change = stream.try_next()
                    if change is not None:
                        _procesar_change(db, change)
                    flush_tarjetas(db)
                    time.sleep(0.1)
        except OperationFailure as e:
            print(f"   ({e})")
            _modo_fallback_polling(client, db)

    except KeyboardInterrupt:
        _resumen()
    finally:
        if client:
            client.close()
        print("🔒 Conexión cerrada.")


if __name__ == "__main__":
    simular_streaming_kafka()