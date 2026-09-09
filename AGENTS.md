# AGENTS — Memoria de trabajo del proyecto

## Redirección

Toda la información de este proyecto (decisiones, progreso, bitácora de trabajo, plan) se almacena en el directorio **[`agents/`](./agents/README.md)**.

Este archivo `AGENTS.md` es solo el **punto de entrada**. Cualquier sesión futura de opencode debe:

1. Leer [`agents/README.md`](./agents/README.md) para ubicarse en la estructura.
2. Cargar el contexto del proyecto (documentos base y notas acumuladas en `agents/`).
3. Registrar todo lo realizado en `agents/` antes de continuar.

`agents/` está excluido de Git (ver `.gitignore`): es memoria interna de trabajo, no se publica.

## Reglas del proyecto

1. **Estructura según la GUÍA.** La implementación vive en `Mongo/` (raíz): `conexion.py`, `scripts/`, `data_lake/{raw,processed,curated}`, `docs/`.
2. **Archivos NO versionados (en `.gitignore`):**
   - `taller-conexion-mongo/` → documentos guía (contexto base), incluido su `.env`.
   - `agents/` → memoria interna de trabajo.
   - `.env` y `.env.*` → secretos. Solo se versiona `.env.example`.
   - `__pycache__/`, `.venv/`, `data_lake/`, archivos de datos (`*.csv`, `*.parquet`, `*.json`).
3. **Secretos:** ÚNICAMENTE en `.env` (cargado por `config.py` desde `taller-conexion-mongo/.env`). Nunca escribir credenciales en código o commits.
4. **Constantes:** la configuración (DB name, colecciones, tamaños, índices) se centraliza en `config.py`; los scripts no repiten `os.getenv`.
5. **Commits pequeños y frecuentes.** Comitear cada cambio lógico (scaffolding, conexión, estructura, datos masivos, ETL, benchmarking) de forma incremental. Mensajes claros en español.

## Contexto del proyecto (resumen)

**Doble entrega del curso IPT (Arquitectura de Datos), corte 1:**

1. **GUÍA PASO A PASO (proyecto integrador, Fase 1)** — documento Word de contexto global: diseño de una arquitectura moderna de datos (≥100 GB) para e-commerce/streaming/IoT. Define 5 semanas (requisitos → arquitectura → particionamiento/replicación → seguridad → costos) y entregables (documento 30-40 págs, diagramas de referencia/lógico/físico, modelo OLTP/OLAP, particionamiento, seguridad, costos, presentación 15 min). Stack objetivo: Kafka → Spark → S3/MinIO (Data Lake) → Cassandra/MongoDB → BigQuery/Snowflake; laboratorio local con Docker.

2. **PARCIAL BD PRIMER CORTE (taller-conexion-mongo)** — Word original + `interpretation-taller.md` (interpretación ya procesada): implementación práctica con **MongoDB Atlas + PyMongo**. Hyperflix, plataforma de streaming de películas, con 5 fases: conexión, modelo OLTP/OLAP, generación masiva (5.000 usuarios, 1.000 películas, 50.000 reproducciones con Faker), ETL vía Aggregation Pipeline y benchmark de consultas con indexación compuesta.

Este repositorio es la implementación real de ambos entregables. Detalle completo en `agents/`.