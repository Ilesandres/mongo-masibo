"""Streaming (simulación de Kafka Consumer) — Terminal 1.

Escucha en tiempo real la colección `reproducciones` mediante MongoDB
Change Streams (patrón Change Data Capture) y procesa cada evento:
INSERT / UPDATE / DELETE, con enriquecimiento (usuario y película)
y una alerta de regla de negocio: reproducción de película larga
completada en una sola sesión (maratón).

Equivalencia con el laboratorio:
    MongoDB Change Streams  -> Kafka (producción)
    Python                  -> Spark Streaming (producción)
    db.reproducciones.watch -> Kafka Consumer
    for change in stream    -> procesamiento continuo
    print(...)              -> alertas / BI / Data Lake

Si el cluster no soporta Change Streams (p. ej. Atlas M0/M2), el script
detecta el error y cae a un modo fallback de polling (degradado).

Cómo usarlo (2 terminales):
    Terminal 1 (esta):  python Mongo/scripts/streaming.py
    Terminal 2:         python Mongo/scripts/generar_reproducciones_streaming.py
"""

import json
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # raíz (config)

import pymongo
from bson import ObjectId
from pymongo.errors import OperationFailure

import config


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


def _alerta_maraton(estado, minutos, duracion, titulo):
    """Regla de negocio: reproducción completada de una película larga (maratón)."""
    if estado != "Completada":
        return
    umbral = duracion if duracion else minutos
    if umbral >= config.MINUTOS_MARATON:
        print(
            f"🚨 ALERTA (maratón): '{titulo}' completada en una sola sesión "
            f"(≥ {config.MINUTOS_MARATON} min de película larga)."
        )


def _mostrar_documento(db, documento, etiqueta):
    codigo = documento.get("codigo_reproduccion", "?")
    estado = documento.get("estado", "?")
    minutos = documento.get("minutos_visualizados") or 0
    pct = documento.get("progreso_pct") or 0.0
    dispositivo = documento.get("dispositivo", "?")
    calidad = documento.get("calidad", "?")
    titulo, duracion = "?", 0
    pelicula = _info_pelicula(db, documento.get("pelicula_id"))
    if pelicula:
        titulo = pelicula.get("titulo", "?")
        duracion = pelicula.get("duracion_min") or 0
    usuario_nombre = _info_usuario(db, documento.get("usuario_id"))
    hora = datetime.now().strftime("%H:%M:%S")
    print(
        f"[{hora}] {etiqueta} | REP {codigo} | {titulo} | {usuario_nombre} | "
        f"{estado} | {minutos} min ({pct:.0f}%) | {dispositivo} | {calidad}"
    )
    _alerta_maraton(estado, minutos, duracion, titulo)


def procesar_cambio(db, change, contador):
    operacion = change.get("operationType", "?")
    hora = datetime.now().strftime("%H:%M:%S")

    if operacion in ("insert", "update"):
        documento = change.get("fullDocument") or {}
        _mostrar_documento(db, documento, operacion.upper())
        if operacion == "update":
            campos = (change.get("updateDescription") or {}).get("updatedFields", {})
            if campos:
                resumen = json.dumps(
                    {k: v for k, v in campos.items() if k != "_id"}, default=str
                )
                print(f"        ↳ cambios: {resumen}")

    elif operacion == "delete":
        doc_key = (change.get("documentKey") or {}).get("_id")
        print(f"[{hora}] DELETE | _id {doc_key} (auditoría)")

    else:
        print(f"[{hora}] {operacion.upper()} | tipo no gestionado")


def _modo_fallback_polling(client, db):
    """Modo degradado para clusters sin Change Streams (Atlas M0/M2)."""
    print("🟡 Este cluster NO soporta Change Streams (típico de Atlas M0/M2).")
    print("   Cambio a modo fallback: polling de novedades cada 1,5 s (sin eventos UPDATE/DELETE).\n")
    vistos = {}
    contador = 0
    try:
        while True:
            ventana = datetime.now() - timedelta(seconds=8)
            cambios = list(
                db.reproducciones.find({"fecha_reproduccion": {"$gte": ventana}}).limit(200)
            )
            for doc in cambios:
                codigo = doc.get("codigo_reproduccion")
                if not codigo:
                    continue
                estado_previo = vistos.get(codigo)
                if estado_previo is None:
                    contador += 1
                    _mostrar_documento(db, doc, "INSERT")
                    vistos[codigo] = doc.get("estado")
                elif doc.get("estado") != estado_previo:
                    contador += 1
                    _mostrar_documento(db, doc, "UPDATE")
                    vistos[codigo] = doc.get("estado")
            if contador and contador % 10 == 0:
                print(
                    f"   📊 [{datetime.now().strftime('%H:%M:%S')}] "
                    f"Polling: {contador} eventos vistos..."
                )
            print("-" * 70)
            time.sleep(1.5)
    except KeyboardInterrupt:
        print("\n⛔ Stream cerrado por el usuario (Ctrl+C).")


def simular_streaming_kafka():
    print("🔵 Iniciando pipeline de streaming (MongoDB Change Streams) — simula Kafka Consumer...\n")
    client = None
    try:
        client = pymongo.MongoClient(config.MONGO_URI, serverSelectionTimeoutMS=8000)
        client.admin.command("ping")
        db = client[config.DB_NAME]
        print(f"👂 Escuchando cambios en la colección '{config.DB_NAME}.reproducciones'...")
        print("   Deja esta terminal abierta.\n")
        print("   ▶ Terminal 2:  python Mongo/scripts/generar_reproducciones_streaming.py\n")
        print("-" * 70)

        try:
            with db.reproducciones.watch(full_document="updateLookup") as stream:
                contador = 0
                for change in stream:
                    contador += 1
                    procesar_cambio(db, change, contador)
                    if contador % 10 == 0:
                        print(
                            f"   📊 [{datetime.now().strftime('%H:%M:%S')}] "
                            f"Micro-batch simulado: {contador} eventos procesados..."
                        )
                    print("-" * 70)
        except OperationFailure as e:
            print(f"   ({e})")
            _modo_fallback_polling(client, db)

    except KeyboardInterrupt:
        print("\n⛔ Stream cerrado por el usuario (Ctrl+C).")
    finally:
        if client:
            client.close()
        print("🔒 Conexión cerrada.")


if __name__ == "__main__":
    simular_streaming_kafka()