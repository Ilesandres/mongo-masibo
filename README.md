# Hyperflix — MongoDB Atlas / PyMongo + Data Lake

Implementación práctica de un sistema de streaming de películas con **MongoDB Atlas + PyMongo** e integración de un **Data Lake a gran escala** (zonas RAW/PROCESSED/CURATED en Parquet). Hyperflix administra usuarios, catálogo de películas, reproducciones, suscripciones, pagos y reseñas en cinco fases, y además construye un pipeline de Data Lake que exporta y transforma toda la información para análisis y BI.

Corresponde al **PARCIAL BD PRIMER CORTE** del curso IPT (Arquitectura de Datos). Las guías y documentos base viven en `taller-conexion-mongo/` y **no se versionan** (ver `.gitignore`).

## Estructura

```
├── Mongo/                          # Implementación real de Hyperflix
│   ├── conexion.py                 # Fase 1 — conexión a Atlas
│   ├── models/                     # MODELOS/ENTIDADES normalizadas (una por archivo)
│   │   ├── usuario.py              #   suscriptor (plan, dirección embebida)
│   │   ├── genero.py               #   catálogo de géneros (referenciado por película)
│   │   ├── director.py             #   catálogo de directores (referenciado por película)
│   │   ├── pelicula.py             #   película normalizada (genero_codigo, director_codigo)
│   │   ├── plan.py                 #   planes de suscripción (Básico/Estándar/Premium)
│   │   ├── suscripcion.py          #   relación Usuario <-> Plan
│   │   ├── pago.py                 #   cobros asociados a una suscripción
│   │   ├── resena.py               #   valoración usuario -> película
│   │   └── reproduccion.py         #   hecho transaccional (ver una película)
│   ├── scripts/
│   │   ├── limpiar_bd.py                  # Reinicio controlado de la base
│   │   ├── crear_estructura.py            # Fase 2 — colecciones + índices + ejemplo
│   │   ├── generar_datos_masivos.py       # Fase 3 — generación a gran escala (~170k docs)
│   │   ├── transformar_oltp_a_olap.py     # Fase 4 — ETL → reproducciones_analiticas
│   │   ├── data_lake_pipeline.py          # Fase 6 — pipeline RAW/PROCESSED/CURATED
│   │   ├── benchmarking_consultas.py      # Fase 5 — índices + 10 consultas OLAP
│   │   ├── streaming.py                   # Fase 7 — Change Streams (escucha = Kafka Consumer)
│   │   ├── generar_reproducciones_streaming.py  # Fase 7 — genera eventos en tiempo real
│   │   ├── spark_jobs.py                  # Fase 8 — 3 Spark Jobs (PySpark) → BI
│   │   ├── data_warehouse.py              # Fase 9 — Star Schema en MongoDB (dim + fact)
│   │   └── dashboard_monitoreo.py         # Dashboard — 6 paneles de monitoreo (PNG)
│   ├── data_lake/{raw,processed,curated}  # Zonas del data lake (no versionado)
│   │   └── curated/spark/                 # Resultados de los Spark Jobs (listos para BI)
│   ├── dashboards/                        # PNG generados por el dashboard (no versionado)
│   └── docs/                   # Documentación del informe
├── config.py                   # Constantes centralizadas (lee secretos desde el .env)
├── requirements.txt
├── .env.example                # Plantilla de secretos
└── taller-conexion-mongo/      # Guías (contexto, NO se sube a Git)
```

## Modelo de datos (entidades normalizadas)

Cada entidad vive en su propio archivo dentro de `Mongo/models/` y expone una función `generar(...)` que construye el documento. Las películas ya **no repiten strings**: referencian `genero_codigo` y `director_codigo` a los catálogos `generos` y `directores`, los cuales se resuelven (desnormalizan a nombres) en la zona PROCESSED del data lake y en la vista OLAP.

| Colección | Descripción | Relación |
| --- | --- | --- |
| `generos` | Catálogo de géneros | 1 a N con `peliculas.genero_codigo` |
| `directores` | Catálogo de directores | 1 a N con `peliculas.director_codigo` |
| `planes` | Planes de suscripción | 1 a N con `suscripciones.codigo_plan` |
| `usuarios` | Suscriptores (con `direccion` embebida) | 1 a N con `suscripciones`/`reproducciones`/`resenas` |
| `peliculas` | Contenido del catálogo (normalizada) | N a 1 con `generos`/`directores` |
| `suscripciones` | Contrato Usuario ↔ Plan | N a 1 con `usuarios` y `planes` |
| `pagos` | Cobros de una suscripción | N a 1 con `suscripciones` |
| `resenas` | Valoraciones de películas | N a 1 con `usuarios` y `peliculas` |
| `reproducciones` | Hecho: un usuario ve una película | N a 1 con `usuarios` y `peliculas` |
| `reproducciones_analiticas` | Vista OLAP (modelo estrella) | generada por la Fase 4 (ETL) |

## Requisitos

- **Python 3.8+** (probado con 3.12 en Windows)
- **MongoDB Atlas** (cluster M0/M10) con credenciales de lectura/escritura
- **Pandas + PyArrow** para la generación de Parquet (Snappy) del data lake
- **Matplotlib + Plotly** para el dashboard de monitoreo (PNG de 6 paneles)
- **Java 11/17/21 (JVM) + `JAVA_HOME`** para Apache Spark (PySpark): `winget install EclipseAdoptium.Temurin.21.JDK`
- Opcional: MongoDB Compass para inspección visual

Hasta 50.000 reproducciones el cluster gratuito M0 responde bien; con 100.000+ toma **varios minutos** en la fase de generación y exportación RAW.

## Configuración

```bash
# 1. Crear el entorno virtual
python -m venv .venv

# 2. Activar (Windows PowerShell)
.venv\Scripts\Activate.ps1
# (Linux/Mac: source .venv/bin/activate)

# 3. Instalar dependencias
pip install -r requirements.txt

# 4. Credenciales: editar taller-conexion-mongo/.env (copiar de .env.example)
#    mongo_uri=mongodb+srv://usuario:contrasena@cluster0.xxxxx.mongodb.net/?retryWrites=true&w=majority
```

> Secreto: **solo** en `.env`. `config.py` carga `taller-conexion-mongo/.env` y expone la constante `MONGO_URI`.

## Pasos de ejecución

Correr siempre desde la raíz del proyecto, con el venv activado:

```bash
# Fase 1 — Probar conexión a Atlas
python Mongo/conexion.py

# Opcional — Limpiar la BD antes de una corrida desde cero (pide confirmación)
python Mongo/scripts/limpiar_bd.py

# Fase 2 — Crear estructura (colecciones, índices, datos de ejemplo)
python Mongo/scripts/crear_estructura.py

# Fase 3 — Generación masiva (10k usuarios, 2k películas, 100k reproducciones, ...)
python Mongo/scripts/generar_datos_masivos.py

# Fase 4 — ETL OLTP → OLAP (modelo estrella)
python Mongo/scripts/transformar_oltp_a_olap.py

# Fase 5 — Benchmarking de 10 consultas analíticas optimizadas (ver sección abajo)
python Mongo/scripts/benchmarking_consultas.py

# Fase 6 — Pipeline de Data Lake (RAW → PROCESSED → CURATED, Parquet/Snappy)
python Mongo/scripts/data_lake_pipeline.py

# Fase 7 — Streaming en tiempo real (ver sección abajo: 2 terminales)
python Mongo/scripts/streaming.py                            # Terminal 1 (escucha)
python Mongo/scripts/generar_reproducciones_streaming.py     # Terminal 2 (genera eventos)

# Fase 8 — Spark Jobs: Apache Spark procesa CURATED y genera tablas para BI
python Mongo/scripts/spark_jobs.py

# Fase 9 — Data Warehouse (Modelo Estrella) en MongoDB: dim_tiempo, dim_cliente,
#          dim_pelicula y fact_consumo a partir de reproducciones_analiticas
python Mongo/scripts/data_warehouse.py

# Dashboard de Monitoreo — genera PNG con 6 paneles (documentos, rendimiento,
#                          costos, tendencia mensual, almacenamiento y resumen)
python Mongo/scripts/dashboard_monitoreo.py
```
### Fase 5 — Benchmarking de 10 consultas analíticas

`benchmarking_consultas.py` crea los **índices compuestos selectivos** (Fase 1) y mide la **latencia** de **10 consultas analíticas OLAP** (Fase 2) sobre `reproducciones_analiticas`, todas con `allowDiskUse=True` (usa disco temporal si la agregación supera la RAM):

1. Reproducciones y minutos totales **mensuales** (serie de tiempo).
2. **Top 5 películas por género** (ranking de catálogo).
3. Rendimiento por **segmento y ciudad** (Completadas; nota: devuelve ~2.000 filas → mayor latencia; lección de clase: en OLAP no solo importa el índice, también el volumen de filas devueltas — un `$limit` lo resolvería).
4. **Valor promedio por dispositivo** (ticket medio del streaming).
5. Reproducciones por **día de la semana** (estacionalidad semanal, `$dayOfWeek`).
6. **Tasa de abandono (Interrumpida)** por dispositivo (`$cond` dentro de `$sum`).
7. **Top 10 clientes VIP** por gasto acumulado (segmento "Completo" + `$limit 10`).
8. Reproducciones **trimestrales** (estacionalidad Q1-Q4, `$ceil` + `$divide`).
9. **Ticket promedio por ciudad y segmento** (Top 15; resuelto por Index Scan con `idx_estado_segmento_ciudad`).
10. **Top 10 películas con mayor rotación** (reproducciones Completadas + `$limit 10`).

Al final imprime el resumen (latencia promedio/máxima e SLA): si el promedio queda **< 500 ms** la conclusión es `RENDIMIENTO ÓPTIMO`. Corrido sobre la BD real (100.000 reproducciones OLAP): promedio **~410 ms**. Los índices usados se centralizan en `config.INDEXES_OLAP` (`idx_fecha`, `idx_genero_valor`, `idx_segmento_ciudad`, `idx_estado_segmento_ciudad`, `idx_dispositivo_estado`).

### Fase 7 — Streaming en tiempo real (2 terminales)

`streaming.py` escucha cambios en la colección `reproducciones` mediante **MongoDB Change Streams** (simula un **Kafka Consumer** + procesamiento continuo estilo Spark), y `generar_reproducciones_streaming.py` genera los eventos (insert/update/delete) tal como lo haría la aplicación web.

> Requisito: Change Streams necesita un **Replica Set**. En Atlas NO está disponible en clusters gratuitos **M0/M2** (usar M10+, un Replica Set local o MongoDB vía Docker). Si el cluster no lo soporta, el consumidor lo detecta y cae automáticamente a un **modo fallback de polling** (degradado: ve el arribo de reproducciones, sin eventos UPDATE/DELETE).

```bash
# TERMINAL 1 — Consumidor: escucha y procesa eventos (dejar abierta)
python Mongo\scripts\streaming.py

# TERMINAL 2 — Productor: genera ~25 reproducciones en tiempo real
python Mongo/scripts/generar_reproducciones_streaming.py
# (opcional) pasar el número de eventos:  python Mongo/scripts/generar_reproducciones_streaming.py 60
```

Cada evento llega a la Terminal 1 en tiempo real (sin reiniciar). Ahí se agrupa el ciclo de vida de cada reproducción (`INSERT` Pendiente → `UPDATE` Completada/Interrumpida; ocasionalmente `DELETE` de auditoría) en una **tarjeta** con la película, el usuario, el dispositivo/calidad, el estado, los minutos y una **barra de progreso**. Incluye una **alerta de regla de negocio** (`🚨 MARATÓN`) cuando una reproducción **completada** es de una **película larga** (≥ `MINUTOS_MARATON` = 120 min) vista en una sola sesión. Al cerrar (Ctrl+C) imprime un **resumen de la sesión** (procesadas, completadas, interrumpidas, eliminadas y maratones).

| Laboratorio (este repo) | Producción |
| --- | --- |
| MongoDB Change Streams | Kafka |
| Python | Spark Streaming |
| `db.reproducciones.watch()` | Kafka Consumer |
| `for change in stream` | Procesamiento continuo |
| `print()` / alerta | Dashboard, alertas o Data Lake |

Este flujo implementa el patrón **Change Data Capture (CDC)**: la BD notifica inserciones/actualizaciones/eliminaciones automáticamente, sin consultas constantes — el mismo fundamento de Kafka + Spark Streaming.

### Fase 8 — Apache Spark: 3 Jobs de procesamiento (PySpark)

`spark_jobs.py` es el **motor Big Data** del proyecto: Apache Spark lee la zona CURATED del Data Lake (Parquet) y ejecuta **3 Spark Jobs** que dejan tablas listas para **BI / Data Warehouse** (cada una como un Parquet en `data_lake/curated/spark/`):

1. **Consumo por dispositivo** — "¿Qué dispositivo genera más consumo e ingresos?" (agregación con `groupBy` + `count/sum/avg`).
2. **Segmentación de clientes** — "¿Qué tipo de clientes tenemos?" (join fact ↔ usuario, métricas por cliente y clasificación con `F.when` → VIP/Premium/Frecuente/Regular).
3. **Evolución mensual** — "¿Cómo evoluciona el consumo por mes?" (`to_date` + `year`/`month` + `groupBy("anio","mes")` → tendencias para dashboards).

> Requisito previo: **Java instalado** (PySpark corre sobre la JVM; `pip install pyspark` no basta). Si falta, el script avisa y corta. Funcionan **Java 11, 17 o 21**.

**Preparar Java en Windows** (una sola vez; requiere permisos de administrador):

```powershell
# 1. Instalar un JDK (OpenJDK 21 — Adoptium/Temurin)
winget install EclipseAdoptium.Temurin.21.JDK

# 2. Definir JAVA_HOME y agregar \bin al PATH — a nivel SISTEMA (todas las máquinas/usuarios)
#    La ruta exacta depende de lo instalado; en este equipo quedó:
#    C:\Program Files\Java\jdk-21.0.12.1
[Environment]::SetEnvironmentVariable("JAVA_HOME", "C:\Program Files\Java\jdk-21.0.12.1", "Machine")
[Environment]::SetEnvironmentVariable("Path",
  [Environment]::GetEnvironmentVariable("Path","Machine") + ";C:\Program Files\Java\jdk-21.0.12.1\bin",
  "Machine")
```

> Está configurado a nivel `Machine` (todos los usuarios). Verifica la ruta con `Get-ChildItem "C:\Program Files\Java"`, y recuerda **abrir una terminal nueva** para que tome las variables. Es necesario haber corrido la **Fase 6** (zona CURATED) antes.

```bash
# Fase 8 — Ejecuta los 3 Spark Jobs sobre el data lake (curated/spark)
python Mongo/scripts/spark_jobs.py
```

Idea clave: **Pandas prepara los datos** (Fase 6, limpieza/enriquecimiento) y **Spark los procesa de forma distribuida** (Fase 8). El mismo código con `local[*]` (todos los núcleos del equipo) escala casi sin cambios a un clúster de varios nodos.

### Fase 9 — Data Warehouse con Modelo Estrella (en MongoDB)

`data_warehouse.py` adapta al dominio de streaming el taller de la **Fase 3 del curso** (modelos dimensionales): aunque MongoDB es NoSQL, el script construye un **Star Schema** con Aggregation Pipelines sobre la vista OLAP `reproducciones_analiticas`, generando 4 colecciones analíticas listas para BI (MongoDB Compass Charts, Atlas SQL, Power BI):

```
                    reproducciones_analiticas
                      (Fuente OLAP enriquecida)
                  /        |         |         \
          dim_tiempo  dim_cliente  dim_pelicula  fact_consumo
        (Fecha,mes,   (Perfil de   (Catálogo y   (Medidas puras:
         año,trimestre, cliente:     director/    solo claves + 
         fin de semana) $first,$sum,$avg) género) minutos y valor)
                  \        |         |         /
                        Consultas BI
                  (Dashboards, SQL, Analytics)
```

Etapas que ejecuta sobre la colección fuente (corrigiendo la guía original):

- **`dim_tiempo`** agrupa por `(anio, mes, dia)` y reconstruye la fecha con `$dateFromParts`; calcula `trimestre` con `{"$ceil": {"$divide": ["$mes", 3]}}` y `fin_semana` con el operador correcto **`$dayOfWeek`** (la guía comparaba `dia==1 || dia==7` sobre el día del mes, lo cual no detecta fines de semana reales).
- **`dim_cliente`** usa `$first` (perfil no duplicado), `$sum` (minutos/gasto totales por suscriptor) y `$avg` + `$round` (valor promedio por reproducción).
- **`dim_pelicula`** agrupa por película con catálogo completo: `$first` de título/género/director + totales de reproducciones, minutos e ingresos.
- **`fact_consumo`** es la tabla de hechos: solo **claves** (`cliente_id`, `pelicula_id`, `fecha_id` por día) y **medidas** (`minutos_visualizados`, `valor_estimado`, `ganancia_estimada`), más contexto ligero de `estado`/`dispositivo`/`calidad`. Reduce duplicación frente a la vista OLAP.
- Los 4 pipelines cierran con **`$merge`** (equivalente a un `INSERT INTO ... ON DUPLICATE KEY`): si el documento existe lo reemplaza, si no, lo inserta — el script es idempotente. `allowDiskUse=True` evita fallos de memoria en volúmenes Big Data.

```bash
# Fase 9 — Construye el Data Warehouse (dim_tiempo, dim_cliente, dim_pelicula, fact_consumo)
python Mongo/scripts/data_warehouse.py
```

La corrida completa deja estas colecciones en `HYPERFLIX-BD`: `generos`, `directores`, `planes`, `usuarios`, `peliculas`, `suscripciones`, `pagos`, `resenas`, `reproducciones`, `reproducciones_analiticas` y las 4 del Data Warehouse (`dim_*` y `fact_consumo`). La Fase 4 conserva el `_id` de cada reproducción y usa `$merge` con `whenMatched: replace`, por lo que puede repetirse sin duplicar datos analíticos. La Fase 6 es idempotente: sobrescribe los archivos `.parquet` de cada zona.

### Dashboard de Monitoreo (6 paneles)

`dashboard_monitoreo.py` genera un **PNG** con un tablero de arquitectura de datos (adaptado de `dashboard.md`), imprime el resumen de `ESTADÍSTICAS DEL DASHBOARD` y deja el archivo en `Mongo/dashboards/dashboard_monitoreo_AÑOmesdía_HoraMinSeg.png` (carpeta no versionada):

```bash
python Mongo/scripts/dashboard_monitoreo.py
```

1. **Documentos por Colección** — barras con el conteo de las 15 colecciones (OLTP + `reproducciones_analiticas` + las 4 del DW).
2. **Rendimiento de Consultas** — latencia de 3 consultas OLAP representativas (mensual, dispositivo, trimestral) contra la línea punteada verde **"Óptimo (< 500 ms)"** (`config.SLA_MS`).
3. **Estimación de Costos Mensuales** — dona con Base (M10) + Almacenamiento + Operaciones (constantes `COSTO_BASE_ATLAS_MES`, `PRECIO_GB_MENSUAL`, `PRECIO_OPERACIONES_MES`).
4. **Tendencia de Consumo Mensual** — línea de ingresos estimados (COP) mes a mes desde la vista OLAP.
5. **Métricas de Almacenamiento** — total documentos / GB / meses con datos normalizados a 0–100%.
6. **Resumen Ejecutivo** — cuadro tipo consola con total documentos, almacenamiento, latencia promedio, costo estimado y estado **OPERATIVO**.

Requiere `matplotlib` y `plotly` (ver `requirements.txt`). En la BD real: **377.706 documentos, ~0,11 GB, promedio ~200 ms, ~$57/mes y 13 meses con datos**, generado en ~6 s.

## Volúmenes de generación (a gran escala)

Configurables en `config.py` (`NUM_*`):

| Entidad | Cantidad |
| --- | --- |
| Géneros | 8 |
| Directores | 300 |
| Planes | 3 |
| Usuarios | 10.000 |
| Películas | 2.000 |
| Suscripciones | 8.000 |
| Pagos | 25.000 |
| Reseñas | 20.000 |
| Reproducciones | 100.000 |

## Data Lake (Fase 6)

`Mongo/scripts/data_lake_pipeline.py` construye el Data Lake adaptado del taller (Parquet + compresión Snappy):

- **Zona RAW** — copia exacta de cada colección de MongoDB (`json_normalize` + `ObjectId → str`), sin modificaciones.
- **Zona PROCESSED** — limpieza y enriquecimiento: reproducciones completadas; fechas descompuestas (`anio`, `mes`, `dia`, `trimestre`); catálogos con referencias resueltas (`película.genero`, `película.director`); usuarios con ciudad/pais y antigüedad; pagos y reseñas enriquecidos. Simula el trabajo que haría Spark.
- **Zona CURATED** — modelo estrella listo para BI: `dim_usuario`, `dim_pelicula`, `dim_fecha`, `fact_reproduccion` + agregados `analitica_temporal`, `analitica_contenido`, `analitica_cliente`, `analitica_pagos` y `analitica_resenas`.

Resultado esperado en pantalla: recuento y tamaño por zona (RAW/PROCESSED/CURATED + total).

## No se versiona (`.gitignore`)

| Ítem | Motivo |
| --- | --- |
| `taller-conexion-mongo/` y `*.docx` | Documentos guía / contexto base |
| `agents/` | Memoria interna de trabajo (opencode) |
| `.env` y `.env.*` | Secretos (solo se versiona `.env.example`) |
| `.venv/`, `__pycache__/`, `data_lake/`, `*.csv`, `*.parquet` | Entorno y datos generados |