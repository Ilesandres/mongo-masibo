# Hyperflix: informe técnico de implementación

## 1. Resumen ejecutivo

Hyperflix es un sistema de streaming de películas implementado con Python, PyMongo,
Faker y MongoDB Atlas. El sistema modela tres entidades operacionales y una colección
analítica:

- `usuarios`: perfiles y características de los suscriptores.
- `peliculas`: catálogo de contenido audiovisual.
- `reproducciones`: eventos de visualización generados por los usuarios.
- `reproducciones_analiticas`: hechos enriquecidos para reportes y consultas OLAP.

El proyecto está organizado en cinco fases ejecutables: conexión, creación de estructura,
generación masiva, transformación OLTP a OLAP y benchmarking. También existe un script
de limpieza controlada para reiniciar la base de datos antes de una nueva corrida.

La ejecución documentada se realizó sobre la base `HYPERFLIX-BD` en MongoDB Atlas y
produjo 5.001 usuarios, 1.001 películas, 50.001 reproducciones y 50.001 registros
analíticos. La diferencia de un registro frente a las cantidades configuradas corresponde
al documento de ejemplo creado durante la fase de estructura.

> **Alcance real:** el código implementa MongoDB Atlas como almacenamiento operativo y
> analítico. Las carpetas del Data Lake están preparadas, pero esta versión todavía no
> exporta documentos a archivos CSV, JSON o Parquet dentro de esas carpetas.

## 2. Objetivos técnicos

El sistema busca demostrar los siguientes conceptos de arquitectura de datos:

1. Conexión segura y reutilizable con MongoDB Atlas.
2. Separación de configuración y secretos mediante variables de entorno.
3. Modelado de datos operacional para usuarios, películas y reproducciones.
4. Inserción masiva por lotes para reducir el número de operaciones de red.
5. Uso de índices únicos para evitar registros duplicados.
6. Construcción de un modelo analítico mediante Aggregation Pipeline.
7. Enriquecimiento de hechos con información de usuarios y películas.
8. Medición de consultas analíticas y comparación de sus latencias.
9. Organización inicial de un Data Lake por zonas `raw`, `processed` y `curated`.

## 3. Arquitectura y flujo general

El flujo completo es el siguiente:

```text
Configuración .env
		|
		v
config.py ---> MongoDB Atlas: HYPERFLIX-BD
					   |
	   +---------------+----------------+
	   |               |                |
	   v               v                v
   usuarios        peliculas     reproducciones
									   |
									   | $lookup + $unwind + $project
									   v
							reproducciones_analiticas
									   |
									   v
							 índices y benchmarks
```

El modelo operacional se denomina OLTP porque recibe y conserva los datos originales de
la aplicación. La colección `reproducciones_analiticas` funciona como una capa OLAP
materializada: contiene campos derivados, dimensiones embebidas y valores calculados para
que las consultas no tengan que repetir los cruces entre colecciones.

## 4. Estructura del proyecto

```text
.
|-- config.py
|-- requirements.txt
|-- README.md
|-- Mongo/
|   |-- conexion.py
|   |-- scripts/
|   |   |-- limpiar_bd.py
|   |   |-- crear_estructura.py
|   |   |-- generar_datos_masivos.py
|   |   |-- transformar_oltp_a_olap.py
|   |   `-- benchmarking_consultas.py
|   |-- data_lake/
|   |   |-- raw/
|   |   |-- processed/
|   |   `-- curated/
|   `-- docs/
|       `-- informe_hyperflix.md
`-- taller-conexion-mongo/
	`-- .env
```

Los scripts se ejecutan desde la raíz del repositorio. Por eso cada script utiliza
`Path(__file__).resolve().parents[2]` para agregar la raíz al `sys.path` y poder importar
`config.py`, aunque el archivo se encuentre dentro de `Mongo/scripts`.

## 5. Dependencias

Las dependencias del archivo `requirements.txt` son:

- `pymongo`: cliente oficial de Python para MongoDB.
- `python-dotenv`: lectura de variables desde el archivo `.env`.
- `faker`: generación de nombres, direcciones, fechas y otros datos de prueba.

El proyecto se ejecuta con un entorno virtual. En Windows, el intérprete utilizado fue
`.venv\\Scripts\\python.exe`.

## 6. Configuración centralizada: `config.py`

`config.py` concentra los valores que comparten todos los scripts. Esto evita repetir
nombres de colecciones, cantidades, tarifas e índices en diferentes archivos.

### 6.1 Importaciones

```python
import os
from pathlib import Path
from dotenv import load_dotenv
```

- `os` permite leer variables de entorno con `os.getenv`.
- `Path` construye rutas compatibles con Windows, Linux y macOS.
- `load_dotenv` carga las variables declaradas en el archivo `.env`.

### 6.2 Carga de secretos y nombre de base

```python
load_dotenv(Path(__file__).parent / "taller-conexion-mongo" / ".env")

MONGO_URI = os.getenv("MONGO_URI") or os.getenv("mongo_uri")
DB_NAME = os.getenv("DB_NAME") or os.getenv("db_name") or "hyperflix_BD"
```

El código acepta tanto `MONGO_URI` como `mongo_uri` porque el archivo utilizado durante
la ejecución tenía la clave en minúsculas. El mismo criterio se aplica a `DB_NAME`.
Si no existe un nombre de base, se utiliza `hyperflix_BD` como valor predeterminado.

La URI no está escrita en ningún script. Esto evita exponer usuario y contraseña en el
código fuente. El archivo `.env` está excluido mediante `.gitignore`.

### 6.3 Colecciones y tamaños

```python
COLECCIONES_OLTP = ["usuarios", "peliculas", "reproducciones"]
COLECCION_OLAP = "reproducciones_analiticas"
NUM_USUARIOS = 5000
NUM_PELICULAS = 1000
NUM_REPRODUCCIONES = 50000
BATCH_SIZE = 1000
```

Estas constantes controlan las cantidades generadas y el tamaño de cada lote. Cambiar
`BATCH_SIZE` modifica el equilibrio entre memoria local y cantidad de solicitudes a Atlas.

### 6.4 Reglas de negocio

```python
TARIFA_POR_MINUTO = 1000
MARGEN_GANANCIA = 0.15
SEGMENTO_COMPLETO_MIN = 90000
SEGMENTO_PARCIAL_MIN = 30000
```

`TARIFA_POR_MINUTO` calcula el valor estimado de una reproducción. `MARGEN_GANANCIA`
calcula una ganancia estimada del 15 %. Los umbrales segmentan el valor de consumo en
`Completo`, `Parcial` y `Corto`.

### 6.5 Índices centralizados

```python
INDEXES_OLTP = {
	"usuarios": [("email", 1)],
	"peliculas": [("codigo_pelicula", 1)],
	"reproducciones": [
		("fecha_reproduccion", -1),
		("usuario_id", 1),
	],
}
```

Esta constante documenta la estrategia operacional. La creación efectiva de índices OLTP
se realiza en `crear_estructura.py`, donde los índices de identidad se declaran como
únicos.

```python
INDEXES_OLAP = [
	("idx_fecha", [("anio", 1), ("mes", 1), ("dia", 1)]),
	("idx_genero_valor", [("pelicula.genero", 1), ("valor_estimado", -1)]),
	("idx_segmento_ciudad", [("usuario.segmento", 1), ("usuario.ciudad", 1)]),
	("idx_estado_segmento_ciudad", [
		("estado", 1),
		("usuario.segmento", 1),
		("usuario.ciudad", 1),
	]),
]
```

El valor `1` representa orden ascendente y `-1` orden descendente. Los índices OLAP se
crean en el script de benchmarking antes de medir las consultas.

## 7. Fase 1: conexión a MongoDB Atlas

Archivo: `Mongo/conexion.py`.

### 7.1 Importaciones y ruta del proyecto

```python
import sys
from pathlib import Path
import pymongo
from pymongo.errors import ConfigurationError, ConnectionFailure, OperationFailure
import config
```

`sys` permite modificar la ruta de importación. `Path` localiza la raíz del proyecto.
`pymongo` proporciona `MongoClient`. Las excepciones importadas separan problemas de
conexión, configuración y autenticación. Finalmente, `config` aporta la URI y el nombre
de la base.

```python
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
```

La primera línea permite imprimir caracteres acentuados en la consola de Windows. La
segunda agrega la raíz del proyecto, que está un nivel por encima de `Mongo/`.

### 7.2 Función `conectar_mongodb`

```python
def conectar_mongodb():
	try:
		client = pymongo.MongoClient(
			config.MONGO_URI,
			serverSelectionTimeoutMS=5000,
		)
		client.admin.command("ping")
		db = client[config.DB_NAME]
		return client, db
	except ConnectionFailure:
		...
	except ConfigurationError as e:
		...
	except OperationFailure as e:
		...
	return None, None
```

`MongoClient` crea el cliente; la conexión real se verifica al ejecutar `ping`. El
parámetro `serverSelectionTimeoutMS=5000` evita esperar indefinidamente si Atlas no está
disponible. MongoDB obtiene la base mediante la notación `client[nombre]`.

La función devuelve una tupla `(client, db)` para que el llamador pueda operar y luego
cerrar el cliente. Si ocurre un error, devuelve `(None, None)` y el programa principal no
intenta cerrar un cliente inexistente.

### 7.3 Ejecución directa

El bloque `if __name__ == "__main__":` ejecuta la prueba de conexión solo cuando el
archivo se lanza directamente. Esto permite importar funciones sin ejecutar el programa
automáticamente.

## 8. Limpieza controlada de la base

Archivo: `Mongo/scripts/limpiar_bd.py`.

La función `limpiar_base_datos` reinicia el entorno mediante `client.drop_database`.
Antes verifica que exista `MONGO_URI`, hace `ping` y exige escribir exactamente
`HYPERFLIX`.

```python
confirmacion = input(
	f"Escribe HYPERFLIX para eliminar la base '{config.DB_NAME}': "
).strip()
if confirmacion != "HYPERFLIX":
	print("Limpieza cancelada; no se modificó la base de datos.")
	return
```

La confirmación reduce el riesgo de borrar la base por accidente. El bloque `finally`
garantiza `client.close()` tanto si la eliminación termina correctamente como si ocurre
una excepción.

Este script debe usarse únicamente cuando se desea comenzar desde cero:

```text
python Mongo/scripts/limpiar_bd.py
```

## 9. Fase 2: creación de estructura OLTP y datos de ejemplo

Archivo: `Mongo/scripts/crear_estructura.py`.

### 9.1 Creación idempotente de colecciones

```python
for col in config.COLECCIONES_OLTP:
	if col not in db.list_collection_names():
		db.create_collection(col)
```

La consulta de nombres evita fallar si el script se ejecuta dos veces. Las colecciones
OLTP son `usuarios`, `peliculas` y `reproducciones`. Luego se crea la colección OLAP
`reproducciones_analiticas` con la misma protección.

### 9.2 Índices OLTP

```python
db.usuarios.create_index([("email", 1)], unique=True)
db.peliculas.create_index([("codigo_pelicula", 1)], unique=True)
db.reproducciones.create_index([("codigo_reproduccion", 1)], unique=True)
db.reproducciones.create_index([("fecha_reproduccion", -1)])
db.reproducciones.create_index([("usuario_id", 1)])
```

- `usuarios.email`: identidad lógica y prevención de correos repetidos.
- `peliculas.codigo_pelicula`: identificador único del catálogo.
- `reproducciones.codigo_reproduccion`: identificador único del evento.
- `fecha_reproduccion`: búsquedas y ordenamientos temporales recientes.
- `usuario_id`: localización rápida del historial de un usuario.

Los índices únicos hacen que MongoDB rechace documentos con la misma clave. La generación
masiva captura `BulkWriteError` para informar duplicados en lugar de detener todo el lote.

### 9.3 Datos de ejemplo y `upsert`

Los tres documentos de prueba se insertan con:

```python
db.usuarios.update_one(
	{"codigo_usuario": usuario_ejemplo["codigo_usuario"]},
	{"$setOnInsert": usuario_ejemplo},
	upsert=True,
)
```

`update_one` busca el documento por su código. `$setOnInsert` solo escribe el documento
si no existe y `upsert=True` lo crea en ese caso. El patrón se repite para películas y
reproducciones, haciendo que la fase sea repetible.

La reproducción de ejemplo obtiene las referencias reales con `find_one` y conserva los
ObjectId de usuario y película:

```python
"usuario_id": db.usuarios.find_one({"codigo_usuario": "USU001"})["_id"],
"pelicula_id": db.peliculas.find_one({"codigo_pelicula": "PEL001"})["_id"],
```

Esto representa una relación entre documentos sin duplicar el usuario ni la película
dentro del evento operacional.

## 10. Fase 3: generación masiva

Archivo: `Mongo/scripts/generar_datos_masivos.py`.

### 10.1 Imports y generador Faker

```python
import random
import time
from faker import Faker
import pymongo
import config

fake = Faker("es_CO")
```

`random` selecciona planes, estados, dispositivos y referencias. `time` mide la duración
total. `Faker("es_CO")` genera datos localizados para Colombia. `pymongo` permite insertar
los lotes y `config` provee tamaños y reglas.

### 10.2 `conectar_bd`

```python
def conectar_bd():
	client = pymongo.MongoClient(config.MONGO_URI)
	return client[config.DB_NAME]
```

La función abre un cliente y retorna directamente el objeto de base. El cliente queda
disponible como `db.client` y se cierra al final de `generar_datos`.

### 10.3 `insertar_en_lotes`

```python
def insertar_en_lotes(coleccion, datos, nombre_entidad):
	for i in range(0, total, config.BATCH_SIZE):
		lote = datos[i:i + config.BATCH_SIZE]
		coleccion.insert_many(lote, ordered=False)
```

La función recibe una colección, una lista de documentos y una etiqueta para los mensajes.
`range` divide la lista en grupos de 1.000. `insert_many` reduce viajes de red y
`ordered=False` permite que los documentos restantes del lote sigan intentando insertarse
si uno produce un error de clave duplicada.

El `except pymongo.errors.BulkWriteError` consulta `e.details['nInserted']` y reporta
cuántos documentos se insertaron y cuántos fueron omitidos.

### 10.4 Generación de usuarios

Los códigos son deterministas:

```python
"codigo_usuario": f"USU{indice + 1:05d}",
"email": f"usuario{indice + 1}@hyperflix.local",
```

Esto evita colisiones aleatorias y facilita repetir la carga. Cada usuario contiene:

- nombre y teléfono generados con Faker;
- dirección anidada con calle, ciudad y país;
- fecha de registro en los últimos dos años;
- estado `activo`;
- plan Básico, Estándar o Premium.

Después de insertar, se consultan todos los `_id` para usarlos como claves foráneas en
las reproducciones:

```python
usuarios_ids = [u["_id"] for u in db.usuarios.find({}, {"_id": 1})]
```

### 10.5 Generación de películas

Cada película recibe un código estable como `PEL00001`, un título de dos palabras, género,
año, duración, director y fecha de estreno. Los géneros usados son Acción, Comedia,
Drama, Ciencia Ficción, Terror, Documental y Romance.

La consulta posterior recupera solo los campos necesarios para las reproducciones:

```python
peliculas_db = list(
	db.peliculas.find({}, {"_id": 1, "titulo": 1, "duracion_min": 1})
)
```

Limitar la proyección reduce memoria y evita traer campos que no se necesitan para crear
los eventos.

### 10.6 Generación de reproducciones

Cada evento relaciona un usuario y una película mediante ObjectId. El estado puede ser
`Completada`, `Interrumpida` o `Pendiente`. Las reproducciones completadas reciben toda
la duración; las demás reciben una cantidad parcial de minutos.

```python
"progreso_pct": round(min(minutos / duracion * 100, 100), 1),
"valor_estimado": round(minutos * config.TARIFA_POR_MINUTO, 2),
```

El porcentaje nunca supera 100. El valor estimado depende del tiempo visualizado y de la
tarifa centralizada. Los eventos se acumulan hasta alcanzar `BATCH_SIZE`, se insertan y
la lista se reinicia para controlar el consumo de memoria.

## 11. Modelo de documentos

### 11.1 Documento `usuarios`

```json
{
  "codigo_usuario": "USU00001",
  "nombre": "Nombre generado",
  "email": "usuario1@hyperflix.local",
  "direccion": {
	"calle": "Dirección",
	"ciudad": "Bogotá",
	"pais": "Colombia"
  },
  "fecha_registro": "fecha BSON",
  "activo": true,
  "plan": "Premium"
}
```

### 11.2 Documento `peliculas`

```json
{
  "codigo_pelicula": "PEL00001",
  "titulo": "Titulo Generado",
  "genero": "Drama",
  "anio": 2020,
  "duracion_min": 120,
  "director": "Director generado",
  "fecha_estreno": "fecha BSON"
}
```

### 11.3 Documento `reproducciones`

```json
{
  "codigo_reproduccion": "REP-2026-000001",
  "usuario_id": "ObjectId de usuarios",
  "pelicula_id": "ObjectId de peliculas",
  "fecha_reproduccion": "fecha BSON",
  "dispositivo": "Smart TV",
  "calidad": "4K",
  "estado": "Completada",
  "minutos_visualizados": 120,
  "progreso_pct": 100.0,
  "valor_estimado": 120000
}
```

## 12. Fase 4: transformación OLTP a OLAP

Archivo: `Mongo/scripts/transformar_oltp_a_olap.py`.

La transformación parte de `reproducciones`, hace dos cruces y materializa un documento
analítico. Se invoca con:

```python
db.reproducciones.aggregate(pipeline, allowDiskUse=True)
```

`allowDiskUse=True` permite que MongoDB utilice almacenamiento temporal si una operación
de agregación supera la memoria disponible del cluster.

### 12.1 `$lookup` de usuarios

```python
{
	"$lookup": {
		"from": "usuarios",
		"localField": "usuario_id",
		"foreignField": "_id",
		"as": "info_usuario",
	}
}
```

Este paso funciona como un JOIN entre la reproducción y el usuario. El resultado siempre
es un arreglo, por eso el pipeline aplica después `$unwind`.

### 12.2 `$lookup` de películas

El segundo `$lookup` utiliza `pelicula_id` contra `_id` de `peliculas`. Así se agregan al
hecho el título, el género y el director.

### 12.3 `$project` y dimensiones derivadas

El proyecto conserva el `_id` original para que cada hecho analítico corresponda a una
reproducción única:

```python
"_id": 1,
"anio": {"$year": "$fecha_reproduccion"},
"mes": {"$month": "$fecha_reproduccion"},
"dia": {"$dayOfMonth": "$fecha_reproduccion"},
```

También crea la dimensión temporal `anio`, `mes` y `dia`, y embebe dos dimensiones:

```python
"usuario": {
	"id": "$info_usuario._id",
	"nombre": "$info_usuario.nombre",
	"ciudad": "$info_usuario.direccion.ciudad",
	"segmento": "..."
},
"pelicula": {
	"id": "$info_pelicula._id",
	"titulo": "$info_pelicula.titulo",
	"genero": "$info_pelicula.genero",
	"director": "$info_pelicula.director"
}
```

El segmento se calcula con `$cond`: valores iguales o superiores a 90.000 son
`Completo`, valores iguales o superiores a 30.000 son `Parcial` y el resto es `Corto`.

La ganancia se calcula dentro de MongoDB:

```python
"ganancia_estimada": {
	"$multiply": ["$valor_estimado", config.MARGEN_GANANCIA]
}
```

### 12.4 `$merge` e idempotencia

```python
{
	"$merge": {
		"into": config.COLECCION_OLAP,
		"on": "_id",
		"whenMatched": "replace",
		"whenNotMatched": "insert",
	}
}
```

Si el hecho ya existe, `replace` reemplaza su versión anterior. Si es nuevo, `insert`
lo agrega. Por conservar el `_id` de la reproducción, la fase puede ejecutarse varias
veces sin duplicar la colección analítica.

### 12.5 Resultado del modelo OLAP

Esta implementación produce un hecho analítico por reproducción. Por eso el resultado
real es 50.001 registros y no 150.000. Una versión futura podría generar varias tablas o
colecciones dimensionales adicionales, pero eso no forma parte del código actual.

## 13. Data Lake

La estructura preparada es:

```text
Mongo/data_lake/
|-- raw/
|-- processed/
`-- curated/
```

### 13.1 Zona `raw`

Representaría los datos tal como llegan desde una fuente: eventos de reproducción,
exportaciones del catálogo o capturas de usuarios sin transformar. En una evolución del
sistema podría contener JSON o Parquet particionado por fecha de ingesta.

### 13.2 Zona `processed`

Representaría datos validados y normalizados: tipos de fecha consistentes, campos
obligatorios, eliminación de duplicados y referencias verificadas.

### 13.3 Zona `curated`

Representaría conjuntos listos para análisis: hechos de reproducción enriquecidos,
agregados por mes, género, ciudad, plan o dispositivo.

### 13.4 Estado de implementación

Las carpetas funcionan actualmente como estructura de proyecto, pero ninguno de los cinco
scripts escribe archivos allí. El pipeline actual mueve datos internamente en MongoDB:
`reproducciones` es la fuente OLTP y `reproducciones_analiticas` es la salida analítica.
Para declarar un Data Lake funcional sería necesario añadir un exportador, por ejemplo:

1. Leer documentos desde MongoDB.
2. Serializar una copia inmutable en `raw`.
3. Validar y limpiar en `processed`.
4. Escribir agregados o hechos analíticos en `curated`.
5. Preferiblemente utilizar Parquet y particiones como `anio=2026/mes=09`.

## 14. Fase 5: benchmarking

Archivo: `Mongo/scripts/benchmarking_consultas.py`.

El script crea primero los índices definidos en `config.INDEXES_OLAP`. Después ejecuta
cinco pipelines y mide cada uno con `time.perf_counter()`, un reloj de alta resolución
adecuado para medir intervalos pequeños.

### 14.1 Consulta mensual

Agrupa por año y mes, suma minutos y cuenta reproducciones. Devuelve 13 filas porque el
conjunto de fechas abarca aproximadamente un año.

### 14.2 Top 5 películas por género

Agrupa por género y título, suma el valor estimado, ordena de mayor a menor y usa
`$slice` para conservar los cinco primeros títulos de cada género.

### 14.3 Rendimiento por segmento y ciudad

Filtra reproducciones completadas, agrupa por `usuario.segmento` y `usuario.ciudad`, y
suma ingresos y ganancia. Es la consulta más costosa porque realiza un agrupamiento y un
ordenamiento sobre muchas combinaciones.

### 14.4 Valor promedio por dispositivo

Filtra reproducciones completadas y calcula promedio, cantidad y valor total para cada
dispositivo: Smart TV, Smartphone, Tablet, PC y Consola.

### 14.5 Reproducciones por día de la semana

`$dayOfWeek` convierte la fecha BSON en un número de 1 a 7. Luego agrupa reproducciones
y valor estimado por día.

### 14.6 Conversión de resultados

```python
resultado_limpio = json.loads(json.dumps(resultados[0], default=str))
```

La conversión permite imprimir ObjectId y fechas BSON como texto JSON sin alterar los
documentos almacenados.

## 15. Índices implementados

### Índices OLTP

| Colección | Índice | Propósito |
| --- | --- | --- |
| `usuarios` | `email` único | Evitar usuarios con el mismo correo |
| `peliculas` | `codigo_pelicula` único | Identificar películas |
| `reproducciones` | `codigo_reproduccion` único | Identificar eventos |
| `reproducciones` | `fecha_reproduccion` descendente | Consultas temporales |
| `reproducciones` | `usuario_id` ascendente | Historial por usuario |

### Índices OLAP

| Nombre | Campos | Uso |
| --- | --- | --- |
| `idx_fecha` | `anio`, `mes`, `dia` | Consultas temporales |
| `idx_genero_valor` | `pelicula.genero`, `valor_estimado` | Comparación por género y valor |
| `idx_segmento_ciudad` | `usuario.segmento`, `usuario.ciudad` | Segmentación geográfica |
| `idx_estado_segmento_ciudad` | `estado`, segmento, ciudad | Filtrado de completadas |

Un índice no garantiza que toda agregación sea menor a 500 ms. Las fases `$group` y
`$sort` deben procesar resultados y pueden seguir siendo costosas, especialmente en un
cluster Atlas de recursos limitados.

## 16. Resultados de ejecución

La corrida se hizo después de eliminar la base con `limpiar_bd.py`.

| Elemento | Resultado |
| --- | ---: |
| Base de datos | `HYPERFLIX-BD` |
| Usuarios | 5.001 |
| Películas | 1.001 |
| Reproducciones | 50.001 |
| Hechos analíticos | 50.001 |
| Tiempo de generación | 221,77 s |
| Tiempo de ETL | 27,67 s |

El usuario de ejemplo y la película de ejemplo explican el registro adicional frente a
los 5.000 y 1.000 documentos generados masivamente.

## 17. Resultados del benchmark

| Consulta | Filas | Latencia |
| --- | ---: | ---: |
| Reproducciones y minutos totales mensuales | 13 | 204,29 ms |
| Top 5 películas por género | 7 | 266,51 ms |
| Rendimiento por segmento y ciudad | 1.995 | 4.601,22 ms |
| Valor promedio por dispositivo | 5 | 250,78 ms |
| Reproducciones por día de la semana | 7 | 254,68 ms |
| **Promedio** | - | **1.115,50 ms** |

La consulta 3 concentra el mayor costo. El promedio no cumple un objetivo estricto de
500 ms y tampoco todas las consultas individuales: la primera, segunda, cuarta y quinta
estuvieron por debajo de 500 ms en esta ejecución, mientras que la tercera fue de
4.601,22 ms. Las latencias dependen de red, carga, caché y recursos del cluster Atlas.

## 18. Manejo de errores y cierre de recursos

El sistema valida la URI antes de ejecutar cada fase. La conexión inicial captura errores
de red, configuración y autenticación. Las inserciones masivas capturan errores de lote
para continuar con documentos válidos. Los clientes MongoDB se cierran al terminar cada
script y la limpieza utiliza `finally` para garantizar el cierre incluso ante errores.

## 19. Reproducibilidad y operación

Para una ejecución completa desde cero:

```text
python Mongo/scripts/limpiar_bd.py
python Mongo/conexion.py
python Mongo/scripts/crear_estructura.py
python Mongo/scripts/generar_datos_masivos.py
python Mongo/scripts/transformar_oltp_a_olap.py
python Mongo/scripts/benchmarking_consultas.py
```

El script de limpieza es opcional. Si no se quiere borrar la base, se puede ejecutar desde
la fase 2: la estructura utiliza comprobaciones de existencia, los documentos de ejemplo
usan `upsert` y el ETL reemplaza hechos por `_id`.

## 20. Limitaciones conocidas

1. La generación utiliza datos sintéticos y no representa tráfico real de producción.
2. La URI depende de un archivo `.env` local y de una red autorizada en Atlas.
3. No existe todavía autenticación de usuarios de Hyperflix a nivel de aplicación.
4. No se implementan pagos, planes con permisos, recomendaciones ni reproducción real de video.
5. El Data Lake solo tiene estructura de carpetas; falta el exportador físico.
6. El OLAP está materializado en una colección y mantiene una fila por reproducción.
7. El benchmark se ejecuta en un cluster de recursos limitados, por lo que sus latencias
   no deben interpretarse como capacidad productiva definitiva.

## 21. Mejoras futuras

- Exportar `reproducciones` a JSON o Parquet en `data_lake/raw`.
- Crear un proceso de validación hacia `processed`.
- Crear agregados diarios y mensuales en `curated`.
- Añadir índices con fechas de consulta cuando las consultas incluyan filtros temporales.
- Medir planes de ejecución con `explain("executionStats")`.
- Evaluar paginación y límites para reportes con miles de filas.
- Separar dimensiones en colecciones analíticas si crece el volumen.
- Añadir pruebas automatizadas para conteos, unicidad e idempotencia.
- Configurar timeouts y opciones TLS explícitas para producción.

## 22. Conclusión

El sistema implementa un pipeline completo y reproducible de streaming en MongoDB Atlas:
conecta, crea el modelo, genera datos, enriquece reproducciones, construye una capa
analítica y mide consultas. La solución cumple el objetivo práctico del taller y deja
preparada la estructura para incorporar un Data Lake físico y una arquitectura analítica
de mayor escala.

Los resultados deben presentarse con sus valores reales: 50.001 hechos OLAP y un promedio
de 1.115,50 ms. No sería correcto afirmar que se generaron 150.000 registros analíticos
ni que todas las consultas quedaron por debajo de 500 ms, porque esas cifras no
corresponden a la ejecución actual del código.
