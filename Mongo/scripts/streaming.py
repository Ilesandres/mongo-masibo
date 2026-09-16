"""Streaming (simulación de Kafka Consumer) — Terminal 1.

Escucha en tiempo real la colección `reproducciones` mediante MongoDB
Change Streams (patrón Change Data Capture) y procesa cada evento:
INSERT / UPDATE / DELETE, con enriquecimiento (usuario y película)
y una alerta de regla de negocio (reproducción completa de alto valor).

Equivalencia con el laboratorio:
    MongoDB Change Streams  -> Kafka (producción)
    Python                  -> Spark Streaming (producción)
    db.reproducciones.watch -> Kafka Consumer
    for change in stream    -> procesamiento continuo
    print(...)              -> alertas / BI / Data Lake

Cómo usarlo (2 terminales):
    Terminal 1 (esta):  python Mongo/scripts/streaming.py
    Terminal 2:         python Mongo/scripts/generar_reproducciones_streaming.py
"""

import json
import sys
from datetime import datetime
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # raíz (config)

import pymongo
from bson import ObjectId
from pymongo.errors import OperationFailure

import config


def _buscar_usuario(db, usuario_id):
    if not usuario_id:
        return "?"
    if isinstance(usuario_id, str):
        try:
            usuario_id = ObjectId(usuario_id)
        except Exception:
            return "?"
    doc = db.usuarios.find_one({"_id": usuario_id}, {"nombre": 1})
    return doc["nombre"] if doc else "?"


def _buscar_pelicula(db, pelicula_id):
    if not pelicula_id:
        return "?"
    if isinstance(pelicula_id, str):
        try:
            pelicula_id = ObjectId(pelicula_id)
        except Exception:
            return "?"
    doc = db.peliculas.find_one({"_id": pelicula_id}, {"titulo": 1})
    return doc["titulo"] if doc else "?"


def procesar_cambio(db, change, contador):
    operacion = change.get("operationType", "?")
    hora = datetime.now().strftime("%H:%M:%S")

    if operacion in ("insert", "update"):
        documento = change.get("fullDocument") or {}
        codigo = documento.get("codigo_reproduccion", "?")
        estado = documento.get("estado", "?")
        valor = documento.get("valor_estimado") or 0
        dispositivo = documento.get("dispositivo", "?")
        usuario_nombre = _buscar_usuario(db, documento.get("usuario_id"))
        pelicula_titulo = _buscar_pelicula(db, documento.get("pelicula_id"))

        print(
            f"[{hora}] {operacion.upper()} | REP {codigo} | {pelicula_titulo} | "
            f"{usuario_nombre} | {estado} | 💰 ${valor:,.0f}"
        )

        if operacion == "update":
            campos = (change.get("updateDescription") or {}).get("updatedFields", {})
            if campos:
                print(f"        ↳ cambios: {json.dumps(campos, default=str)}")

        # Regla de negocio en tiempo real: reproducción completa de alto valor
        if estado == "Completada" and valor >= config.SEGMENTO_COMPLETO_MIN:
            print(
                f"🚨 ALERTA: reproducción completa de alto valor "
                f"— ${valor:,.0f} en {dispositivo}."
            )

    elif operacion == "delete":
        doc_key = (change.get("documentKey") or {}).get("_id")
        print(f"[{hora}] DELETE | _id {doc_key} (auditoría)")

    else:
        print(f"[{hora}] {operacion.upper()} | tipo no gestionado")


def simular_streaming_kafka():
    print("🔵 Iniciando pipeline de streaming (MongoDB Change Streams) — simula Kafka Consumer...\n")
    client = None
    try:
        client = pymongo.MongoClient(config.MONGO_URI, serverSelectionTimeoutMS=8000)
        db = client[config.DB_NAME]
        db.admin.command("ping")
        print(f"👂 Escuchando cambios en la colección '{config.DB_NAME}.reproducciones'...")
        print("   Deja esta terminal abierta.\n")
        print("   ▶ Terminal 2:  python Mongo/scripts/generar_reproducciones_streaming.py\n")
        print("-" * 70)

        contador = 0
        with db.reproducciones.watch(full_document="updateLookup") as stream:
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
        print("❌ Error de Change Streams.")
        print("   ▶ Mongo Change Streams requiere un Replica Set. En Atlas NO está disponible en clusters M0/M2.")
        print("   ▶ Usa un cluster M10+, un Replica Set local o MongoDB vía Docker.")
        print(f"   Detalle: {e}")
    except KeyboardInterrupt:
        print("\n⛔ Stream cerrado por el usuario (Ctrl+C).")
    finally:
        if client:
            client.close()
        print("🔒 Conexión cerrada.")


if __name__ == "__main__":
    simular_streaming_kafka()