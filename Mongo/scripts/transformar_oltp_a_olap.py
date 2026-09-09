import sys
import time
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pymongo

import config


def transformar_datos():
    print("🔄 Iniciando transformación de datos OLTP a OLAP (Modelo Estrella)...\n")
    client = pymongo.MongoClient(config.MONGO_URI)
    db = client[config.DB_NAME]
    inicio = time.time()

    pipeline = [
        {"$lookup": {
            "from": "clientes",
            "localField": "cliente_id",
            "foreignField": "_id",
            "as": "info_cliente",
        }},
        {"$unwind": "$info_cliente"},
        {"$unwind": "$items"},
        {"$lookup": {
            "from": "productos",
            "localField": "items.producto_id",
            "foreignField": "_id",
            "as": "info_producto",
        }},
        {"$unwind": "$info_producto"},
        {"$project": {
            "_id": 0,
            "fecha_venta": 1,
            "anio": {"$year": "$fecha_venta"},
            "mes": {"$month": "$fecha_venta"},
            "dia": {"$dayOfMonth": "$fecha_venta"},
            "cliente": {
                "id": "$info_cliente._id",
                "nombre": "$info_cliente.nombre",
                "ciudad": "$info_cliente.direccion.ciudad",
                "segmento": {
                    "$cond": [
                        {"$gte": ["$total", 5000000]},
                        "Premium",
                        {
                            "$cond": [
                                {"$gte": ["$total", 1000000]},
                                "Frecuente",
                                "Regular",
                            ]
                        },
                    ]
                },
            },
            "producto": {
                "id": "$info_producto._id",
                "nombre": "$info_producto.nombre",
                "categoria": "$info_producto.categoria",
                "marca": "$info_producto.proveedor",
            },
            "cantidad": "$items.cantidad",
            "precio_unitario": "$items.precio_unitario",
            "total_venta": "$items.subtotal",
            "ganancia_estimada": {"$multiply": ["$items.subtotal", config.MARGEN_GANANCIA]},
            "numero_factura": 1,
            "metodo_pago": 1,
            "estado": 1,
        }},
        {"$merge": {
            "into": config.COLECCION_OLAP,
            "on": "_id",
            "whenNotMatched": "insert",
        }},
    ]

    print("⚙️ Ejecutando Aggregation Pipeline...")
    list(db.ventas.aggregate(pipeline, allowDiskUse=True))
    tiempo_total = time.time() - inicio
    total_analitico = db[config.COLECCION_OLAP].count_documents({})
    print("=" * 60)
    print("🎉 ¡TRANSFORMACIÓN OLTP A OLAP COMPLETADA!")
    print(f"⏱️  Tiempo de procesamiento: {tiempo_total:.2f} segundos")
    print(f"📊 Registros analíticos generados: {total_analitico}")
    print("=" * 60)
    client.close()


if __name__ == "__main__":
    transformar_datos()