import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from datetime import datetime

import pymongo

import config


def crear_estructura_ventas():
    client = pymongo.MongoClient(config.MONGO_URI)
    db = client[config.DB_NAME]
    print("🏗️ Creando estructura de base de datos de ventas...\n")

    print("📦 Creando colecciones transaccionales (OLTP)...")
    for col in config.COLECCIONES_OLTP:
        db.create_collection(col)
        print(f"  ✅ Colección '{col}' creada")

    print("\n🔍 Creando índices...")
    db.clientes.create_index([("email", 1)], unique=True)
    db.productos.create_index([("sku", 1)], unique=True)
    db.ventas.create_index([("fecha_venta", -1)])
    db.ventas.create_index([("cliente_id", 1)])
    print("  ✅ Índices creados")

    print("\n📝 Insertando datos de prueba...")
    cliente_ejemplo = {
        "codigo_cliente": "CLI001",
        "nombre": "Juan Pérez",
        "email": "juan.perez@email.com",
        "telefono": "3001234567",
        "direccion": {
            "calle": "Calle 123 #45-67",
            "ciudad": "Bogotá",
            "pais": "Colombia",
        },
        "fecha_registro": datetime.now(),
        "activo": True,
    }
    db.clientes.insert_one(cliente_ejemplo)
    print("  ✅ Cliente insertado")

    producto_ejemplo = {
        "sku": "PROD001",
        "nombre": "Laptop Dell XPS 15",
        "categoria": "Electrónica",
        "precio_unitario": 4500000,
        "stock": 25,
        "proveedor": "Dell Colombia S.A.S",
        "fecha_creacion": datetime.now(),
    }
    db.productos.insert_one(producto_ejemplo)
    print("  ✅ Producto insertado")

    venta_ejemplo = {
        "numero_factura": "FAC-2026-0001",
        "cliente_id": db.clientes.find_one({"codigo_cliente": "CLI001"})["_id"],
        "fecha_venta": datetime.now(),
        "items": [
            {
                "producto_id": db.productos.find_one({"sku": "PROD001"})["_id"],
                "cantidad": 1,
                "precio_unitario": 4500000,
                "subtotal": 4500000,
            }
        ],
        "total": 4500000,
        "metodo_pago": "Tarjeta de Crédito",
        "estado": "Completada",
    }
    db.ventas.insert_one(venta_ejemplo)
    print("  ✅ Venta insertada")

    print("\n📊 Creando colección analítica (OLAP)...")
    db.create_collection(config.COLECCION_OLAP)
    print(f"  ✅ Colección '{config.COLECCION_OLAP}' creada")

    print("\n✅ Estructura de ventas creada exitosamente en Atlas!")
    print("🔍 Abre MongoDB Compass para ver las colecciones creadas.")
    client.close()


if __name__ == "__main__":
    crear_estructura_ventas()