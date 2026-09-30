# -*- coding: utf-8 -*-
"""
iac_setup.py — Orquestador de Entorno y Configuración como Código (Configuration as Code).

Adaptado al sistema Hyperflix (MongoDB Atlas + Data Lake). Cubre:

    1. Validar la versión de Python (>= 3.12).
    2. Validar/instalar el entorno virtual (.venv) con su versión correcta.
    3. Verificar e instalar las dependencias (requirements.txt).
    4. Provisionamiento local: estructura del Data Lake (raw/processed/curated/spark).
    5. Validar el .env (el real que carga config.py) y, si falta, generar .env.template
       con datos de ejemplo y mostrar WARNINGs/alertas.
    6. Health Check: conexión real a MongoDB Atlas (solo si el .env es válido).

Ejecutar:  py iac_setup.py        (o: python iac_setup.py)
"""
import shutil
import subprocess
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parent
PY_MIN = (3, 12)
ENV_FILE = ROOT / "taller-conexion-mongo" / ".env"
ENV_TEMPLATE = ROOT / ".env.template"
REQUIREMENTS = ROOT / "requirements.txt"

VENV_DIR = ROOT / ".venv"
VENV_PY = VENV_DIR / ("Scripts" if sys.platform == "win32" else "bin") / "python.exe"

RESULTADOS = []


def resumen(nombre, ok, detalle):
    estado = "[OK]" if ok else "[KO]"
    RESULTADOS.append((nombre, ok))
    print(f"  {estado} {nombre}: {detalle}")


def python_version(executable):
    salida = subprocess.run(
        [str(executable), "-c", "import sys; print('.'.join(map(str, sys.version_info[:3])))"],
        capture_output=True,
        text=True,
    )
    return salida.stdout.strip()


def crear_venv(executable):
    print("  [+] Creando entorno virtual (.venv) ...")
    proc = subprocess.run([str(executable), "-m", "venv", str(VENV_DIR)])
    return proc.returncode == 0


# ── 1/6  Python ─────────────────────────────────────────────
def fase_python():
    print("\n[1/6] Validando versión de Python ...")
    v = sys.version_info
    actual = f"{v.major}.{v.minor}.{v.micro}"
    minimo = f"{PY_MIN[0]}.{PY_MIN[1]}"
    if v >= PY_MIN:
        resumen("Python", True, f"versión {actual} (mínimo {minimo}).")
    else:
        resumen("Python", False, f"versión {actual} es MENOR que {minimo} requerido.")


# ── 2/6  Entorno virtual (.venv) ────────────────────────────
def fase_venv():
    print("\n[2/6] Validando entorno virtual (.venv) ...")
    if not VENV_PY.exists():
        ok = crear_venv(sys.executable)
        resumen(".venv", ok, "creado desde cero." if ok else "no se pudo crear.")
        return
    version = python_version(VENV_PY)
    v = tuple(int(p) for p in version.split(".") if p.isdigit())
    if v and v >= PY_MIN:
        resumen(".venv", True, f"ya existe con Python {version} (correcto).")
    else:
        print("  [ALERTA] El .venv tiene una versión de Python incompatible; se recreará.")
        shutil.rmtree(VENV_DIR, ignore_errors=True)
        ok = crear_venv(sys.executable)
        resumen(".venv", ok, "recreado con la versión actual de Python." if ok else "falló al recrear.")


# ── 3/6  Dependencias ───────────────────────────────────────
def fase_dependencias():
    print("\n[3/6] Verificando dependencias (requirements.txt) ...")
    if not REQUIREMENTS.exists():
        resumen("Dependencias", False, f"no existe {REQUIREMENTS.name}.")
        return
    print("  [+] Instalando/verificando paquetes ...")
    proc = subprocess.run(
        [str(VENV_PY), "-m", "pip", "install", "-q", "-r", str(REQUIREMENTS)],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        print("  " + "\n  ".join(proc.stderr.strip().splitlines()[-8:]))
        resumen("Dependencias", False, "pip install falló.")
        return
    proc = subprocess.run(
        [str(VENV_PY), "-m", "pip", "check"], capture_output=True, text=True
    )
    ok = proc.returncode == 0
    resumen("Dependencias", ok, "instaladas y consistentes (pip check OK)." if ok else "conflictos detectados (pip check).")


# ── 4/6  Data Lake ──────────────────────────────────────────
def fase_datalake():
    print("\n[4/6] Provisionando estructura del Data Lake ...")
    base = ROOT / "Mongo" / "data_lake"
    zonas = [base / "raw", base / "processed", base / "curated", base / "curated" / "spark"]
    for zona in zonas:
        zona.mkdir(parents=True, exist_ok=True)
    resumen("Data Lake", True, ", ".join(str(z.relative_to(ROOT)) for z in zonas) + ".")


# ── 5/6  .env ───────────────────────────────────────────────
TEMPLATE_ENV = (
    "# Copia este archivo a taller-conexion-mongo/.env y rellena con tus credenciales reales de MongoDB Atlas.\n"
    "# (Es el .env que lee config.py). NUNCA subir .env a Git.\n"
    "\n"
    "MONGO_URI=mongodb+srv://tu_usuario:tu_contrasena@cluster0.xxxxx.mongodb.net/?retryWrites=true&w=majority\n"
    "DB_NAME=hyperflix_BD\n"
)


def leer_env(clave):
    if not ENV_FILE.exists():
        return None
    for linea in ENV_FILE.read_text(encoding="utf-8").splitlines():
        linea = linea.strip()
        if linea.startswith(clave + "="):
            valor = linea.split("=", 1)[1].strip().strip('"').strip("'")
            if valor:
                return valor
    return None


def fase_env():
    print("\n[5/6] Validando archivo .env ...")
    if not ENV_FILE.exists():
        ENV_TEMPLATE.write_text(TEMPLATE_ENV, encoding="utf-8")
        print("  [ALERTA] No existe taller-conexion-mongo/.env.")
        print(f"  [WARNING] Se generó datos de ejemplo en: {ENV_TEMPLATE.name}")
        print("  -> Copia .env.template a taller-conexion-mongo/.env, rellena MONGO_URI y vuelve a correr.")
        resumen(".env", False, "falta el archivo con credenciales; se creó .env.template.")
        return False
    uri = leer_env("MONGO_URI") or leer_env("mongo_uri")
    if not uri:
        print("  [ALERTA] .env existe pero MONGO_URI está vacía.")
        resumen(".env", False, "MONGO_URI vacía o sin credenciales.")
        return False
    resumen(".env", True, "presente y con MONGO_URI definida.")
    return True


# ── 6/6  Health Check MongoDB Atlas ─────────────────────────
HEALTH_CODE = """
import sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
import config, pymongo
host = pymongo.uri_parser.parse_uri(config.MONGO_URI)["nodelist"][0][0]
cliente = pymongo.MongoClient(config.MONGO_URI, serverSelectionTimeoutMS=5000)
cliente.admin.command("ping")
cliente.close()
print("OK|%s|%s" % (host, config.DB_NAME))
"""


def fase_health():
    print("\n[6/6] Health Check: conexión a MongoDB Atlas ...")
    if not VENV_PY.exists():
        resumen("Conexión Atlas", False, "no existe el .venv para ejecutar el ping.")
        return
    proc = subprocess.run(
        [str(VENV_PY), "-c", HEALTH_CODE, str(ROOT)],
        capture_output=True,
        text=True,
    )
    salida = proc.stdout.strip()
    if proc.returncode == 0 and salida.startswith("OK|"):
        _, host, bd = salida.split("|")
        resumen("Conexión Atlas", True, f"ping OK hacia host {host} (BD: {bd}).")
    else:
        detalle = proc.stderr.strip().splitlines()
        detalle = detalle[-1].strip() if detalle else proc.returncode
        resumen("Conexión Atlas", False, f"falló ({detalle}): revisa URI, Access List y credenciales.")


# ── Ejecución ────────────────────────────────────────────────
def main():
    print("=" * 64)
    print("iac_setup.py — Configuración como Código (Hyperflix / MongoDB Atlas)")
    print("=" * 64)

    fase_python()
    fase_venv()
    fase_dependencias()
    fase_datalake()
    env_ok = fase_env()
    if env_ok:
        fase_health()

    faltas = [nombre for nombre, ok in RESULTADOS if not ok]
    print("\n" + "=" * 64)
    print("RESUMEN")
    for nombre, ok in RESULTADOS:
        print(f"  {'✓' if ok else '✗'}  {nombre}")

    if not faltas:
        print("\n¡ENTORNO LISTO! Puedes ejecutar las fases del proyecto.")
        print("  [Hint nube] Para reproducir Atlas en código:  .\\deploy_infra_nube.ps1")
    else:
        print("\nFALTAN pasos: " + ", ".join(faltas))
        if not env_ok:
            print("  Revisa el aviso del .env: crea .env.template ya generado, rellénalo y repite.")
    print("=" * 64)
    sys.exit(0 if not faltas else 1)


if __name__ == "__main__":
    main()