# -*- coding: utf-8 -*-
"""Fase 10 — Data Warehouse en la nube (Google BigQuery / Snowflake).

Lee el modelo estrella de la zona **CURATED** del Data Lake (Parquet, en disco
o en S3) y lo carga en el Data Warehouse de la nube con los **mismos nombres de
tablas de la Fase 9** (`data_warehouse.py`): `dim_tiempo`, `dim_cliente`,
`dim_pelicula` y `fact_consumo`.

Principios de diseño (no romper flujos):

  * **NUNCA escribe en MongoDB**: las Fases 1-5, 7 y 9 quedan intactas.
  * El destino lo decide `DW_BACKEND` en el `.env`
    (`none` = apagado por defecto, `bigquery`, `snowflake`).
  * `--solo-validar` recorre todo el ETL **sin conexión a la nube** ni
    librerías extra: sirve para verificar lectura + transformación.
  * `--limite N` recorta el hecho para una primera corrida de prueba
    (smoke test barato antes de subir los millones de filas).

Uso:
    python Mongo/scripts/data_warehouse_cloud.py --solo-validar
    python Mongo/scripts/data_warehouse_cloud.py --limite 1000
    python Mongo/scripts/data_warehouse_cloud.py
    python Mongo/scripts/data_warehouse_cloud.py --modo append
"""
import argparse
import sys
import time
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # raíz (config)
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # Mongo/ (almacenamiento, dw_cloud)

import pandas as pd

import almacenamiento
import config
import dw_cloud

# Orden de carga: dimensiones primero, el hecho al final.
ORDEN_CARGA = ["dim_tiempo", "dim_cliente", "dim_pelicula", "fact_consumo"]

# Columnas del hecho con el esquema de la Fase 9 (fact_consumo) + claves del lake
COLUMNAS_FACT = [
    "codigo_reproduccion", "fecha_id", "fecha_reproduccion", "cliente_id", "pelicula_id",
    "fecha_key", "usuario_key", "pelicula_key", "anio", "mes", "estado", "dispositivo",
    "calidad", "minutos_visualizados", "progreso_pct", "valor_estimado", "ganancia_estimada",
]


def _log(mensaje):
    """Imprime con flush para ver el estado en tiempo real."""
    print(mensaje, flush=True)


def _segmento_por_valor(valor):
    """Misma regla de negocio que Fase 4/6/9 (config.SEGMENTO_*)."""
    if valor >= config.SEGMENTO_COMPLETO_MIN:
        return "Completo"
    if valor >= config.SEGMENTO_PARCIAL_MIN:
        return "Parcial"
    return "Corto"


def _tabla_sql(nombre):
    """Identificador de tabla listo para el SQL del backend (BigQuery usa `backticks`)."""
    identificador = dw_cloud.tabla_id(nombre)
    return f"`{identificador}`" if dw_cloud.es_bigquery() else identificador


# ── Lectura de la zona CURATED ─────────────────────────────
def _leer_curated(nombre, origen):
    try:
        df = almacenamiento.leer_parquet("curated", nombre)
    except (FileNotFoundError, OSError) as error:
        raise SystemExit(
            f"❌ No se encontró '{nombre}.parquet' en {almacenamiento.destino('curated')}.\n"
            "   Ejecuta primero la Fase 6 (data_lake_pipeline.py) o genera el Data Lake\n"
            "   sin MongoDB:  python Mongo/scripts/generar_data_lake_sintetico.py"
        ) from error
    _log(f"   ✓ {nombre:<22} → {len(df):>10,} filas  ({origen})")
    return df


# ── Transformación CURATED → esquema del DW (Fase 9) ──────
def preparar_tablas(limite=None):
    """Construye las 4 tablas del DW a partir de la zona CURATED.

    Devuelve ``{nombre_tabla_dw: DataFrame}`` con los nombres de la Fase 9.
    """
    destino_lake = almacenamiento.destino("curated")
    _log(f"⬇️  Leyendo modelo estrella de la zona CURATED ({destino_lake})...")

    fact = _leer_curated("fact_reproduccion", destino_lake)
    dim_fecha = _leer_curated("dim_fecha", destino_lake)
    dim_usuario = _leer_curated("dim_usuario", destino_lake)
    dim_pelicula = _leer_curated("dim_pelicula", destino_lake)

    if limite:
        fact = fact.head(limite).copy()
        _log(f"   ✂️  --limite {limite}: el hecho queda en {len(fact):,} filas (las dims se leen completas)")

    # ── fact_consumo: hecho con claves + medidas (esquema de la Fase 9) ──
    fact = fact.merge(dim_fecha[["fecha_key", "fecha"]], on="fecha_key", how="left")
    fact["fecha_id"] = fact["fecha"].dt.date  # DATE en BigQuery → columna de partición
    fact = fact.rename(columns={"usuario_id": "cliente_id"})
    faltantes = [c for c in COLUMNAS_FACT if c not in fact.columns]
    if faltantes:
        raise SystemExit(f"❌ 'fact_reproduccion' no tiene las columnas esperadas: {faltantes}")
    fact_consumo = fact[COLUMNAS_FACT].copy()
    sin_fecha = int(fact_consumo["fecha_id"].isna().sum())
    if sin_fecha:
        _log(f"   ⚠️  {sin_fecha:,} hechos sin fecha_key equivalente en dim_fecha (quedan en la partición NULL)")

    # ── dim_tiempo: fecha + atributos derivados (fin de semana ISO: 6=sáb, 7=dom) ──
    dim_tiempo = dim_fecha.copy()
    dim_tiempo["fin_semana"] = dim_tiempo["dia_semana"].ge(6).map({True: "Sí", False: "No"})
    dim_tiempo.sort_values("fecha", inplace=True)

    # ── dim_cliente: perfil del suscriptor + métricas de consumo del hecho ──
    # Orden por fecha para que "segmento" (primera fila del cliente) sea determinista.
    fact_ordenado = fact.sort_values(["usuario_key", "fecha_reproduccion"])
    fact_ordenado["segmento_fila"] = fact_ordenado["valor_estimado"].apply(_segmento_por_valor)
    metricas_cliente = (
        fact_ordenado.groupby("usuario_key", sort=False)
        .agg(
            segmento=("segmento_fila", "first"),
            reproducciones=("codigo_reproduccion", "count"),
            minutos_totales=("minutos_visualizados", "sum"),
            gasto_total=("valor_estimado", "sum"),
            valor_promedio=("valor_estimado", "mean"),
        )
        .reset_index()
    )
    metricas_cliente["gasto_total"] = metricas_cliente["gasto_total"].round(0)
    metricas_cliente["valor_promedio"] = metricas_cliente["valor_promedio"].round(0)

    dim_cliente = dim_usuario.merge(metricas_cliente, on="usuario_key", how="left")
    dim_cliente["segmento"] = dim_cliente["segmento"].fillna("Sin actividad")
    for columna in ("reproducciones", "minutos_totales"):
        dim_cliente[columna] = dim_cliente[columna].fillna(0).astype("int64")
    for columna in ("gasto_total", "valor_promedio"):
        dim_cliente[columna] = dim_cliente[columna].fillna(0.0).astype("float64")

    # ── dim_pelicula: catálogo + totales de reproducciones/minutos/ingresos ──
    metricas_pelicula = (
        fact.groupby("pelicula_key", sort=False)
        .agg(
            reproducciones=("codigo_reproduccion", "count"),
            minutos_totales=("minutos_visualizados", "sum"),
            ingresos_totales=("valor_estimado", "sum"),
        )
        .reset_index()
    )
    metricas_pelicula["ingresos_totales"] = metricas_pelicula["ingresos_totales"].round(0)

    dim_pelicula_out = dim_pelicula.merge(metricas_pelicula, on="pelicula_key", how="left")
    for columna in ("reproducciones", "minutos_totales"):
        dim_pelicula_out[columna] = dim_pelicula_out[columna].fillna(0).astype("int64")
    dim_pelicula_out["ingresos_totales"] = (
        dim_pelicula_out["ingresos_totales"].fillna(0.0).astype("float64")
    )

    tablas_fuente = {
        "fact_reproduccion": fact_consumo,
        "dim_fecha": dim_tiempo,
        "dim_usuario": dim_cliente,
        "dim_pelicula": dim_pelicula_out,
    }
    return {config.TABLAS_DW_NUBE[origen]: df for origen, df in tablas_fuente.items()}


# ── Validación SIN nube (no requiere credenciales) ─────────
def validar_sin_nube(tablas):
    """Imprime el plan de carga (tablas, filas, columnas y tamaño estimado)."""
    _log("")
    _log("📐 Mapeo CURATED → Data Warehouse (mismos nombres que la Fase 9):")
    for origen, dw in config.TABLAS_DW_NUBE.items():
        _log(f"     {origen:<22} → {dw}")

    _log("")
    _log("📋 Plan de carga (sin tocar la nube):")
    total_filas = 0
    total_mem_mb = 0.0
    for nombre in ORDEN_CARGA:
        df = tablas[nombre]
        mem_mb = df.memory_usage(deep=True).sum() / 1e6
        total_filas += len(df)
        total_mem_mb += mem_mb
        extra = ""
        if nombre == "fact_consumo" and dw_cloud.activo() and dw_cloud.es_bigquery():
            modo = config.DW_PARTICION_MODO
            detalle = (
                "fecha de negocio" if modo == "fecha"
                else "fecha de ingestión" if modo == "ingesta"
                else "auto (sandbox→ingesta / con facturación→fecha)"
            )
            extra = f"  [PARTICIÓN={detalle} + CLUSTER {config.DW_CLUSTER}]"
        _log(f"   • {nombre:<14} → {len(df):>10,} filas × {len(df.columns):>2} col "
             f"(~{mem_mb:,.1f} MB en RAM){extra}")
    _log(f"   {'TOTAL':<14} → {total_filas:>10,} filas (~{total_mem_mb:,.1f} MB en RAM)")
    _log("")
    _log("✅ Validación OK: lectura de CURATED + transformación al esquema del DW correctas.")
    _log(f"   Backend actual: DW_BACKEND={config.DW_BACKEND} "
         + ("(capa apagada — activa 'bigquery' en el .env para cargar)" if not dw_cloud.activo() else ""))
    _log("   Siguiente paso: python Mongo/scripts/data_warehouse_cloud.py")


# ── Carga a la nube ────────────────────────────────────────
def cargar_en_la_nube(tablas, modo):
    _log("")
    _log(f"☁️  Conectando al Data Warehouse (backend: {dw_cloud.backend()})...")
    cliente = dw_cloud.conectar()
    try:
        dw_cloud.asegurar_dataset(cliente)
        _log(f"   ✓ Conectado. Destino: {dw_cloud.tabla_id('<tabla>')}")
        if modo == "replace":
            _log("   Modo REPLACE: las tablas se sobrescriben (idempotente, sin duplicados).")
        else:
            _log("   Modo APPEND: se agregan filas (carga incremental).")

        total = 0
        for nombre in ORDEN_CARGA:
            df = tablas[nombre]
            inicio = time.perf_counter()
            _log(f"   ⬆️  {nombre}: cargando {len(df):,} filas...")
            filas, destino = dw_cloud.cargar_dataframe(cliente, df, nombre, modo)
            total += filas
            _log(f"      ✅ {destino} → {filas:,} filas en {time.perf_counter() - inicio:.1f}s")

        _log("")
        _log(f"🎉 ¡DATA WAREHOUSE CARGADO! ({total:,} filas en total)")

        # Validación ligera con guardia de costo (dry-run antes de gastar cuota)
        sql = (
            f"SELECT COUNT(*) AS filas, COUNT(DISTINCT cliente_id) AS clientes, "
            f"COUNT(DISTINCT pelicula_id) AS peliculas "
            f"FROM {_tabla_sql('fact_consumo')}"
        )
        estimado = dw_cloud.estimar_consulta(cliente, sql)
        if estimado is not None:
            tope = config.BQ_MAX_BYTES_BILLED
            _log(f"🔎 Dry-run de validación: procesaría {estimado / 1e6:.3f} MB "
                 f"(tope BQ_MAX_BYTES_BILLED = {f'{tope:,} bytes' if tope else 'sin tope'})")
            if tope and estimado > tope:
                _log("⚠️  La validación supera el tope configurado; se omite para no gastar cuota.")
                return
        try:
            filas = dw_cloud.consultar(cliente, sql)[0]
            _log(f"   ✓ fact_consumo verificada → {filas['filas']:,} filas | "
                 f"{filas['clientes']:,} clientes | {filas['peliculas']:,} películas")
        except Exception as error:  # la validación nunca debe romper la carga
            _log(f"⚠️  No se pudo validar la tabla (la carga ya terminó): {error}")
        try:
            _log(f"   🗂  Tablas en el DW: {', '.join(dw_cloud.listar_tablas(cliente))}")
        except Exception:
            pass
    finally:
        dw_cloud.cierre(cliente)


# ── CLI ────────────────────────────────────────────────────
def _argumentos():
    parser = argparse.ArgumentParser(
        description="Fase 10 — ETL: Data Lake CURATED → Data Warehouse en la nube"
    )
    parser.add_argument(
        "--modo", choices=["replace", "append"], default="replace",
        help="replace = sobrescribe las tablas (idempotente, por defecto); "
             "append = agrega filas (carga incremental)",
    )
    parser.add_argument(
        "--limite", type=int, default=None, metavar="N",
        help="recorta el hecho a N filas (prueba de humo antes de subir todo)",
    )
    parser.add_argument(
        "--solo-validar", action="store_true",
        help="lee y transforma el Data Lake SIN tocar la nube (no requiere credenciales)",
    )
    return parser.parse_args()


def main():
    args = _argumentos()

    if not dw_cloud.activo() and not args.solo_validar:
        _log(dw_cloud.apagado())
        return 0

    _log("🔄 Fase 10 — Data Lake CURATED → Data Warehouse en la nube\n")
    inicio = time.time()
    tablas = preparar_tablas(args.limite)

    if args.solo_validar:
        validar_sin_nube(tablas)
        return 0

    cargar_en_la_nube(tablas, args.modo)
    _log(f"⏱️  Tiempo total: {time.time() - inicio:.2f} segundos")
    return 0


if __name__ == "__main__":
    sys.exit(main())
