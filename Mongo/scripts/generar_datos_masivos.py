import random
import sys
import time
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pymongo
from faker import Faker

import config

fake = Faker('es_CO')


def conectar_bd():
    client = pymongo.MongoClient(config.MONGO_URI)
    return client[config.DB_NAME]


def insertar_en_lotes(coleccion, datos, nombre_entidad):
    total = len(datos)
    print(f"📦 Insertando {total} {nombre_entidad} en lotes de {config.BATCH_SIZE}...")
    for i in range(0, total, config.BATCH_SIZE):
        lote = datos[i:i + config.BATCH_SIZE]
        try:
            coleccion.insert_many(lote, ordered=False)
            progreso = min(i + config.BATCH_SIZE, total)
            print(f"  ➡️ Progreso: {progreso}/{total} ({(progreso / total) * 100:.1f}%)")
        except pymongo.errors.BulkWriteError as e:
            insertados = e.details.get('nInserted', 0)
            progreso = min(i + config.BATCH_SIZE, total)
            print(f"  ⚠️ Progreso: {progreso}/{total} (Se omitieron {len(lote) - insertados} duplicados)")
    print(f"  ✅ Proceso de {nombre_entidad} finalizado.\n")


def generar_datos():
    print("🚀 Iniciando generación de datos masivos para MongoDB Atlas...\n")
    db = conectar_bd()
    inicio_total = time.time()

    print("👤 Generando clientes...")
    clientes = []
    for _ in range(config.NUM_CLIENTES):
        clientes.append({
            "codigo_cliente": f"CLI{random.randint(10000, 99999)}",
            "nombre": fake.name(),
            "email": f"{fake.user_name()}{random.randint(1000, 9999)}@{fake.free_email_domain()}",
            "telefono": fake.phone_number(),
            "direccion": {
                "calle": fake.street_address(),
                "ciudad": fake.city(),
                "pais": "Colombia",
            },
            "fecha_registro": fake.date_time_between(start_date='-2y', end_date='now'),
            "activo": random.choice([True, True, True, False]),
        })
    insertar_en_lotes(db.clientes, clientes, "clientes")
    clientes_ids = [c["_id"] for c in db.clientes.find({}, {"_id": 1})]

    print("📦 Generando productos...")
    categorias = ["Electrónica", "Hogar", "Ropa", "Deportes", "Juguetes", "Libros"]
    productos = []
    for _ in range(config.NUM_PRODUCTOS):
        productos.append({
            "sku": f"PROD{random.randint(10000, 99999)}",
            "nombre": f"{fake.word().capitalize()} {fake.word().capitalize()}",
            "categoria": random.choice(categorias),
            "precio_unitario": round(random.uniform(10000, 5000000), 2),
            "stock": random.randint(0, 500),
            "proveedor": fake.company(),
            "fecha_creacion": fake.date_time_between(start_date='-1y', end_date='now'),
        })
    insertar_en_lotes(db.productos, productos, "productos")
    productos_db = list(db.productos.find({}, {"_id": 1, "precio_unitario": 1, "nombre": 1}))

    print("💰 Generando ventas (esto puede tomar unos minutos)...")
    metodos_pago = ["Tarjeta de Crédito", "Tarjeta Débito", "Nequi", "DaviPlata", "Efectivo", "PSE"]
    estados = ["Completada", "Completada", "Completada", "Pendiente", "Cancelada"]
    ventas = []
    for _ in range(config.NUM_VENTAS):
        num_items = random.randint(1, 5)
        items_venta = random.sample(productos_db, num_items)
        total_venta = 0
        items_detalle = []
        for prod in items_venta:
            cantidad = random.randint(1, 3)
            subtotal = prod["precio_unitario"] * cantidad
            total_venta += subtotal
            items_detalle.append({
                "producto_id": prod["_id"],
                "nombre_producto": prod["nombre"],
                "cantidad": cantidad,
                "precio_unitario": prod["precio_unitario"],
                "subtotal": round(subtotal, 2),
            })
        ventas.append({
            "numero_factura": f"FAC-{fake.year()}-{random.randint(100000, 999999)}",
            "cliente_id": random.choice(clientes_ids),
            "fecha_venta": fake.date_time_between(start_date='-1y', end_date='now'),
            "items": items_detalle,
            "total": round(total_venta, 2),
            "metodo_pago": random.choice(metodos_pago),
            "estado": random.choice(estados),
        })
        if len(ventas) >= config.BATCH_SIZE:
            insertar_en_lotes(db.ventas, ventas, "ventas (lote)")
            ventas = []
    if len(ventas) > 0:
        insertar_en_lotes(db.ventas, ventas, "ventas (lote final)")

    tiempo_total = time.time() - inicio_total
    print("=" * 50)
    print("🎉 ¡GENERACIÓN DE DATOS COMPLETADA!")
    print(f"⏱️  Tiempo total de ejecución: {tiempo_total:.2f} segundos")
    print(f"📊 Clientes en BD: {db.clientes.count_documents({})}")
    print(f"📦 Productos en BD: {db.productos.count_documents({})}")
    print(f"💰 Ventas en BD: {db.ventas.count_documents({})}")
    print("=" * 50)
    db.client.close()


if __name__ == "__main__":
    generar_datos()