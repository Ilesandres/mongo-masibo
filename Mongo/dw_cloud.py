# -*- coding: utf-8 -*-
"""dw_cloud.py — Abstracción del Data Warehouse en la nube (Fase 10).

Mismo patrón que ``almacenamiento.py`` para el Data Lake: los scripts NO
escriben "a mano" contra el DW, siempre pasan por este módulo. Según
``DW_BACKEND`` en el ``.env``:

    DW_BACKEND=none       -> capa APAGADA (por defecto). El proyecto se
                             comporta EXACTAMENTE igual que antes de esta fase.
    DW_BACKEND=bigquery   -> Google BigQuery (Sandbox gratuita, sin tarjeta).
    DW_BACKEND=snowflake  -> Snowflake (Free Trial 30 días / USD 400).

Arquitectura resultante (doc: Mongo/docs/data_warehouse_cloud.md):

    MongoDB Atlas (OLTP) ──> Data Lake Parquet ──> Data Warehouse (OLAP)
       Fases 1-5, 7            Fases 6, 8              Fase 10  <── este módulo
        (Fase 9 construye además un prototipo de DW dentro de MongoDB)

Nada de esto escribe en MongoDB: el flujo OLTP/OLAP existente queda intacto.

Variables del ``.env`` que usa:
    DW_BACKEND                    none | bigquery | snowflake
    BQ_PROJECT                    proyecto GCP (obligatorio con bigquery)
    BQ_DATASET                    dataset (por defecto: hyperflix)
    BQ_LOCATION                   ubicación del dataset (por defecto: US)
    BQ_MAX_BYTES_BILLED           tope de bytes por consulta (0 = sin tope)
    GOOGLE_APPLICATION_CREDENTIALS  ruta al JSON de la service account
    SNOWFLAKE_ACCOUNT/USER/PASSWORD/WAREHOUSE/DATABASE/SCHEMA/ROLE
"""
from pathlib import Path

import config

# Solo lectura/escritura en BigQuery (mínimo necesario)
_SCOPE_BQ = "https://www.googleapis.com/auth/bigquery"


# ── Backend ────────────────────────────────────────────────
def backend():
    """Backend configurado para el Data Warehouse ('none', 'bigquery', 'snowflake')."""
    return config.DW_BACKEND


def activo():
    """¿La capa de Data Warehouse en la nube está habilitada?"""
    return config.DW_BACKEND in ("bigquery", "snowflake")


def es_bigquery():
    return config.DW_BACKEND == "bigquery"


def tabla_id(nombre):
    """Identificador completo de una tabla en el DW configurado."""
    if es_bigquery():
        return f"{config.BQ_PROJECT}.{config.BQ_DATASET}.{nombre}"
    return f"{config.SNOWFLAKE_DATABASE}.{config.SNOWFLAKE_SCHEMA}.{nombre}"


def apagado():
    """Mensaje claro cuando DW_BACKEND=none (se muestra y el script sale sin error)."""
    return (
        "⚠️  DW_BACKEND=none → la capa de Data Warehouse en la nube está APAGADA "
        "(por defecto el proyecto funciona igual que siempre).\n"
        "   Para cargar a la nube: activa en el .env  DW_BACKEND=bigquery "
        "(Sandbox sin tarjeta) o DW_BACKEND=snowflake.\n"
        "   Mientras tanto puedes probar el ETL sin conexión: "
        "python Mongo/scripts/data_warehouse_cloud.py --solo-validar"
    )


# ── Importación protegida de librerías opcionales ──────────
def _importar_bigquery():
    try:
        from google.cloud import bigquery
    except ImportError as error:
        raise RuntimeError(
            "Falta la librería 'google-cloud-bigquery'. Instálala con:\n"
            "   pip install -r requirements-dw.txt"
        ) from error
    return bigquery


def _importar_snowflake():
    try:
        import snowflake.connector
        from snowflake.connector.pandas_tools import write_pandas
    except ImportError as error:
        raise RuntimeError(
            "Falta la librería 'snowflake-connector-python'. Instálala con:\n"
            "   pip install -r requirements-dw.txt"
        ) from error
    return snowflake.connector, write_pandas


# ── Conexión ───────────────────────────────────────────────
def _credenciales_bigquery():
    """Service account (GOOGLE_APPLICATION_CREDENTIALS) o ADC de gcloud."""
    ruta = config.GOOGLE_APPLICATION_CREDENTIALS
    if ruta:
        if not Path(ruta).exists():
            raise RuntimeError(
                f"GOOGLE_APPLICATION_CREDENTIALS='{ruta}' no existe. "
                "Descarga el JSON de la service account y corrige la ruta en el .env."
            )
        from google.oauth2 import service_account

        return service_account.Credentials.from_service_account_file(ruta, scopes=[_SCOPE_BQ])

    try:
        from google.auth import default

        credenciales, _ = default(scopes=[_SCOPE_BQ])
        return credenciales
    except Exception as error:  # DefaultCredentialsError u otras
        raise RuntimeError(
            "No se encontraron credenciales de Google. Define en el .env:\n"
            "   GOOGLE_APPLICATION_CREDENTIALS=C:\\ruta\\credenciales-dw.json\n"
            "(JSON de la service account con roles BigQuery Data Editor + Job User),\n"
            "o ejecuta 'gcloud auth application-default login' para usar las ADC."
        ) from error


def conectar():
    """Devuelve el cliente/segunda conexión del DW configurado."""
    if not activo():
        raise RuntimeError(apagado())
    if es_bigquery():
        bigquery = _importar_bigquery()
        if not config.BQ_PROJECT:
            raise RuntimeError(
                "Falta BQ_PROJECT en el .env (proyecto de Google Cloud donde "
                "vive el dataset de BigQuery). Ej. BQ_PROJECT=mi-proyecto-123"
            )
        return bigquery.Client(project=config.BQ_PROJECT, credentials=_credenciales_bigquery())

    snowflake, _ = _importar_snowflake()
    if not (config.SNOWFLAKE_ACCOUNT and config.SNOWFLAKE_USER and config.SNOWFLAKE_PASSWORD):
        raise RuntimeError(
            "DW_BACKEND=snowflake necesita SNOWFLAKE_ACCOUNT, SNOWFLAKE_USER y "
            "SNOWFLAKE_PASSWORD en el .env (Free Trial: cuenta, usuario y contraseña)."
        )
    return snowflake.connect(
        account=config.SNOWFLAKE_ACCOUNT,
        user=config.SNOWFLAKE_USER,
        password=config.SNOWFLAKE_PASSWORD,
        warehouse=config.SNOWFLAKE_WAREHOUSE,
        database=config.SNOWFLAKE_DATABASE,
        schema=config.SNOWFLAKE_SCHEMA,
        role=config.SNOWFLAKE_ROLE or None,
    )


# ── Catálogo de tablas ─────────────────────────────────────
def _dataset_ref():
    return f"{config.BQ_PROJECT}.{config.BQ_DATASET}"


def es_sandbox(client):
    """¿El proyecto está en BigQuery Sandbox (sin facturación)?

    En modo sandbox Google aplica por defecto `default_*_expiration_ms` de
    60 días al dataset y NO permite quitarlo (la API responde: *"Table
    expiration time must be less than 60 days while in sandbox mode"*).
    Detectamos el modo por esas expiraciones heredadas.
    """
    if not es_bigquery():
        return False
    try:
        dataset = client.get_dataset(_dataset_ref())
    except Exception:
        return False
    return bool(dataset.default_table_expiration_ms) or bool(dataset.default_partition_expiration_ms)


def resolver_particion(client):
    """Decide cómo particionar `fact_consumo`: fecha de negocio o fecha de ingestión.

    Devuelve ``(campo_o_None, descripcion)``; ``None`` = partición por ingestión
    (``_PARTITIONTIME``), que es la única segura en sandbox porque los 60 días
    de retención corren desde la carga y no desde la fecha del dato.
    """
    modo = config.DW_PARTICION_MODO
    if modo == "fecha":
        return config.DW_PARTICION, f"fecha de negocio ({config.DW_PARTICION})"
    if modo == "ingesta":
        return None, "fecha de ingestión (_PARTITIONTIME)"
    # auto
    if es_sandbox(client):
        return None, "fecha de ingestión (_PARTITIONTIME) — proyecto en SANDBOX (retención 60 días)"
    return config.DW_PARTICION, f"fecha de negocio ({config.DW_PARTICION})"


_AVISOS = {"sandbox": False}


def asegurar_dataset(client):
    """Crea el dataset de BigQuery si no existe (idempotente) e informa su política."""
    if not es_bigquery():
        return
    bigquery = _importar_bigquery()
    dataset = bigquery.Dataset(_dataset_ref())
    dataset.location = config.BQ_LOCATION
    dataset = client.create_dataset(dataset, exists_ok=True)
    if (dataset.default_table_expiration_ms or dataset.default_partition_expiration_ms) and not _AVISOS["sandbox"]:
        _AVISOS["sandbox"] = True
        dias = (dataset.default_table_expiration_ms or dataset.default_partition_expiration_ms) / 86_400_000
        print(
            f"   ℹ️  SANDBOX detectado: el dataset aplica expiración de {dias:.0f} días a "
            "tablas/particiones (no se puede quitar sin facturación).\n"
            "      El ETL usará partición por INGESTA para que ningún dato cargado hoy "
            "desaparezca antes de tiempo."
        )


def tabla_existe(client, nombre):
    """¿Existe la tabla en el DW?"""
    if es_bigquery():
        from google.api_core.exceptions import NotFound

        try:
            client.get_table(tabla_id(nombre))
            return True
        except NotFound:
            return False

    _, _ = _importar_snowflake()
    cursor = client.cursor()
    try:
        cursor.execute(
            "SELECT COUNT(*) FROM %s.INFORMATION_SCHEMA.TABLES WHERE TABLE_NAME = %%s"
            % config.SNOWFLAKE_DATABASE,
            (nombre.upper(),),
        )
        return cursor.fetchone()[0] > 0
    finally:
        cursor.close()


def listar_tablas(client):
    """Nombres de las tablas del DW (para el resumen)."""
    if es_bigquery():
        return sorted(
            t.table_id
            for t in client.list_tables(config.BQ_DATASET)
        )

    _, _ = _importar_snowflake()
    cursor = client.cursor()
    try:
        cursor.execute(
            "SELECT TABLE_NAME FROM %s.INFORMATION_SCHEMA.TABLES WHERE TABLE_SCHEMA = %%s"
            % (config.SNOWFLAKE_DATABASE,),
            (config.SNOWFLAKE_SCHEMA.upper(),),
        )
        return sorted(f[0] for f in cursor.fetchall())
    finally:
        cursor.close()


# ── Carga de datos ─────────────────────────────────────────
def cargar_dataframe(client, df, nombre, modo="replace"):
    """Carga un DataFrame en la tabla ``nombre`` del DW.

    modo="replace" → sobrescribe la tabla (idempotente, igual que $merge en Mongo)
    modo="append"  → agrega filas (para cargas incrementales)
    Devuelve una tupla (filas_cargadas, descripcion_del_destino).
    """
    if es_bigquery():
        return _cargar_bigquery(client, df, nombre, modo)
    return _cargar_snowflake(client, df, nombre, modo)


def _esquema_particion_actual(client, destino):
    """``(campo_particion, clustering)`` de la tabla existente, o ``None`` si no existe."""
    from google.api_core.exceptions import NotFound

    try:
        tabla = client.get_table(destino)
    except NotFound:
        return None
    tp = tabla.time_partitioning
    return (tp.field if tp else None, tuple(tabla.clustering_fields or []))


def _cargar_bigquery(client, df, nombre, modo):
    bigquery = _importar_bigquery()
    asegurar_dataset(client)

    job_config = bigquery.LoadJobConfig()
    job_config.write_disposition = (
        bigquery.WriteDisposition.WRITE_TRUNCATE
        if modo == "replace"
        else bigquery.WriteDisposition.WRITE_APPEND
    )
    job_config.autodetect = True

    destino = tabla_id(nombre)

    if nombre == "fact_consumo" and config.DW_PARTICION in df.columns:
        # Particionamiento + clustering (rúbrica). En SANDBOX la partición por fecha
        # de negocio haría desaparecer las particiones con >60 días apenas se cargan,
        # así que `resolver_particion` elige la fecha de ingestión en ese modo.
        campo_particion, descripcion = resolver_particion(client)
        clustering = list(config.DW_CLUSTER)
        if campo_particion is None:
            clustering = [config.DW_PARTICION] + clustering  # la fecha de negocio queda agrupada
        clustering = [c for c in clustering if c in df.columns]

        actual = _esquema_particion_actual(client, destino)
        if actual is not None and actual != (campo_particion, tuple(clustering)):
            if modo != "replace":
                raise RuntimeError(
                    f"'{destino}' tiene un esquema de partición distinto al deseado "
                    f"(actual={actual}, deseado={(campo_particion, tuple(clustering))}). "
                    "BigQuery no permite cambiarlo en caliente: corre primero con "
                    "'--modo replace' para recrear la tabla."
                )
            # La tabla se recrea (con --modo replace igual se sobrescribía).
            client.delete_table(destino)
            print(f"   ♻️  Tabla '{destino}' recreada para aplicar {descripcion} "
                  f"+ CLUSTER BY {clustering}.", flush=True)

        job_config.time_partitioning = bigquery.TimePartitioning(field=campo_particion)
        if clustering:
            job_config.clustering_fields = clustering
        print(f"   📐 Partición por {descripcion} | CLUSTER BY {clustering}", flush=True)

    job = client.load_table_from_dataframe(df, destino, job_config=job_config)
    job.result()  # bloquea hasta terminar
    return len(df), destino


def _cargar_snowflake(client, df, nombre, modo):
    _, write_pandas = _importar_snowflake()
    destino = tabla_id(nombre)

    if modo == "replace":
        cursor = client.cursor()
        try:
            cursor.execute(f"DROP TABLE IF EXISTS {destino}")
        finally:
            cursor.close()

    # auto_create_table=True crea la tabla con el esquema del DataFrame si no existe;
    # si ya existe, write_pandas solo agrega filas (modo append).
    existe = tabla_existe(client, nombre)
    ok, _, n_filas, _ = write_pandas(
        client,
        df,
        nombre,
        database=config.SNOWFLAKE_DATABASE,
        schema=config.SNOWFLAKE_SCHEMA,
        auto_create_table=not existe,
        overwrite=False,
    )
    if not ok:
        raise RuntimeError(f"Snowflake rechazó la carga de '{destino}' (write_pandas ok=False).")
    return int(n_filas), destino


# ── Consultas (validación / benchmark) ─────────────────────
def estimar_consulta(client, sql):
    """Dry-run: bytes que costaría la consulta, sin ejecutarla (None si no aplica)."""
    if not es_bigquery():
        return None
    bigquery = _importar_bigquery()
    job_config = bigquery.QueryJobConfig(dry_run=True, use_query_cache=False)
    job = client.query(sql, job_config=job_config)
    return job.total_bytes_processed


def consultar(client, sql):
    """Ejecuta SQL y devuelve filas como lista de dicts.

    En BigQuery aplica ``BQ_MAX_BYTES_BILLED`` (guarda de costo) si está definido.
    """
    if es_bigquery():
        bigquery = _importar_bigquery()
        job_config = bigquery.QueryJobConfig()
        if config.BQ_MAX_BYTES_BILLED:
            job_config.maximum_bytes_billed = config.BQ_MAX_BYTES_BILLED
        job = client.query(sql, job_config=job_config)
        return [dict(fila) for fila in job.result()]

    snowflake, _ = _importar_snowflake()
    cursor = client.cursor(snowflake.connector.DictCursor)
    try:
        cursor.execute(sql)
        return list(cursor.fetchall())
    finally:
        cursor.close()


def cierre(client):
    """Cierra la conexión si el backend lo permite."""
    if not es_bigquery():
        client.close()
