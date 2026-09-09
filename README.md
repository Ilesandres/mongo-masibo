# Almacenamiento Masivo — MongoDB Atlas / PyMongo

Implementación práctica de una arquitectura de datos con **MongoDB Atlas + PyMongo**: sistema de ventas con 5 fases (conexión, modelo OLTP/OLAP, generación masiva, ETL y benchmarking).

Corresponde al **PARCIAL BD PRIMER CORTE** del curso IPT (Arquitectura de Datos). Las guías y documentos base viven en `taller-conexion-mongo/` y **no se versionan** (ver `.gitignore`).

## Estructura

```
├── Mongo/                      # Implementación real
│   ├── conexion.py             # Fase 1 — conexión a Atlas
│   ├── scripts/
│   │   ├── crear_estructura.py            # Fase 2 — colecciones + índices + ejemplo
│   │   ├── generar_datos_masivos.py       # Fase 3 — 5.000 clientes, 1.000 productos, 50.000 ventas
│   │   ├── transformar_oltp_a_olap.py     # Fase 4 — ETL (Aggregation Pipeline) → modelo estrella
│   │   └── benchmarking_consultas.py      # Fase 5 — índices compuestos + 5 consultas + latencias
│   ├── data_lake/{raw,processed,curated} # Zonas del data lake (no versionado)
│   └── docs/                   # Documentación del informe
├── config.py                   # Constantes centralizadas (lee secretos desde el .env)
├── requirements.txt
├── .env.example                # Plantilla de secretos
└── taller-conexion-mongo/      # Guías (contexto, NO se sube a Git)
```

## Requisitos

- **Python 3.8+** (probado con 3.12 en Windows)
- **MongoDB Atlas** (cluster M0/M10) con credenciales de lectura/escritura
- Opcional: MongoDB Compass para inspección visual

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

## Pasos de ejecución (5 fases)

Correr siempre desde la raíz del proyecto, con el venv activado:

```bash
# Fase 1 — Probar conexión a Atlas
python Mongo/conexion.py

# Fase 2 — Crear estructura (colecciones, índices, datos de ejemplo)
python Mongo/scripts/crear_estructura.py

# Fase 3 — Generación masiva (puede tomar unos minutos)
python Mongo/scripts/generar_datos_masivos.py

# Fase 4 — ETL OLTP → OLAP (modelo estrella)
python Mongo/scripts/transformar_oltp_a_olap.py

# Fase 5 — Benchmarking de consultas analíticas
python Mongo/scripts/benchmarking_consultas.py
```

## No se versiona (`.gitignore`)

| Ítem | Motivo |
| --- | --- |
| `taller-conexion-mongo/` y `*.docx` | Documentos guía / contexto base |
| `agents/` | Memoria interna de trabajo (opencode) |
| `.env` y `.env.*` | Secretos (solo se versiona `.env.example`) |
| `.venv/`, `__pycache__/`, `data_lake/`, `*.csv`, `*.parquet` | Entorno y datos generados |