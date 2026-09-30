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
    7. (Automático) Validación NUBE en código: si el .env es válido, ejecuta
       deploy_infra_nube.ps1 (terraform init -> plan -> apply contra MongoDB Atlas).
       Se omite con el flag --sin-nube.

Ejecutar:  py iac_setup.py          (o: python iac_setup.py)
           py iac_setup.py --sin-nube   (solo local, sin validación de nube)
"""
import argparse
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
NUBE_SCRIPT = ROOT / "deploy_infra_nube.ps1"

VENV_DIR = ROOT / ".venv"
VENV_PY = VENV_DIR / ("Scripts" if sys.platform == "win32" else "bin") / "python.exe"

RESULTADOS = []

# ── Estética / stickers con aspecto "generado por IA" ────────
EMOJIS = {
    "python": "🐍", "venv": "🧪", "deps": "📦", "lake": "🗃️",
    "env": "🔑", "health": "📡", "nube": "☁️", "ok": "🚀", "alerta": "⚠️",
}

# Colores ANSI (solo activos si la salida es una terminal real).
_RESET = "\033[0m"
_CYAN = "\033[96m"
_GREEN = "\033[92m"
_YELLOW = "\033[93m"
_RED = "\033[91m"
_MAGENTA = "\033[95m"
_BOLD = "\033[1m"
if not sys.stdout.isatty():
    _RESET = _CYAN = _GREEN = _YELLOW = _RED = _MAGENTA = _BOLD = ""


def banner():
    print()
    print(f"  {_MAGENTA}╔═══════════════════════════════════════════════════════════════╗{_RESET}")
    print(f"  {_MAGENTA}║{_RESET}{_BOLD}   ✨  HYPERFLIX · CONFIGURATION AS CODE  ✨{_RESET}                      {_MAGENTA}║{_RESET}")
    print(f"  {_MAGENTA}║{_RESET}   {EMOJIS['python']} Python   {EMOJIS['venv']} venv   {EMOJIS['deps']} deps   {EMOJIS['lake']} data lake          {_MAGENTA}║{_RESET}")
    print(f"  {_MAGENTA}║{_RESET}   {EMOJIS['env']} .env   {EMOJIS['health']} Atlas   {EMOJIS['nube']} nube automática          {_MAGENTA}║{_RESET}")
    print(f"  {_MAGENTA}╚═══════════════════════════════════════════════════════════════╝{_RESET}")


def encabezado(numero, total, emoji, titulo):
    print()
    print(f"  {_CYAN}╭─ {emoji}  PASO {numero}/{total} · {titulo}{_RESET}")
    print(f"  {_CYAN}│{_RESET}")


def barra_progreso(ok_count, total):
    ancho = 20
    lleno = round(ancho * ok_count / total) if total else 0
    pct = round(100 * ok_count / total) if total else 0
    relleno = "█" * lleno + "░" * (ancho - lleno)
    color = _GREEN if pct >= 100 else (_YELLOW if pct >= 50 else _RED)
    print(f"  {color}Progreso: [{relleno}] {pct}% ({ok_count}/{total} pasos){_RESET}")


def resumen(nombre, ok, detalle):
    RESULTADOS.append((nombre, ok))
    marca = f"{_GREEN}✔{_RESET}" if ok else f"{_RED}✘{_RESET}"
    print(f"  {marca}  {nombre}: {detalle}")


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


# ── 1/7  Python ─────────────────────────────────────────────
def fase_python():
    encabezado(1, 7, EMOJIS["python"], "Validar versión de Python (>= 3.12)")
    v = sys.version_info
    actual = f"{v.major}.{v.minor}.{v.micro}"
    minimo = f"{PY_MIN[0]}.{PY_MIN[1]}"
    if v >= PY_MIN:
        resumen("Python", True, f"versión {actual} (mínimo {minimo}).")
    else:
        resumen("Python", False, f"versión {actual} es MENOR que {minimo} requerido.")


# ── 2/7  Entorno virtual (.venv) ───────────────────────────
def fase_venv():
    encabezado(2, 7, EMOJIS["venv"], "Entorno virtual (.venv)")
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


# ── 3/7  Dependencias ───────────────────────────────────────
def fase_dependencias():
    encabezado(3, 7, EMOJIS["deps"], "Verificar dependencias (requirements.txt)")
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


# ── 4/7  Data Lake ──────────────────────────────────────────
def fase_datalake():
    encabezado(4, 7, EMOJIS["lake"], "Provisionar estructura del Data Lake")
    base = ROOT / "Mongo" / "data_lake"
    zonas = [base / "raw", base / "processed", base / "curated", base / "curated" / "spark"]
    for zona in zonas:
        zona.mkdir(parents=True, exist_ok=True)
    resumen("Data Lake", True, ", ".join(str(z.relative_to(ROOT)) for z in zonas) + ".")


# ── 5/7  .env ───────────────────────────────────────────────
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
    encabezado(5, 7, EMOJIS["env"], "Validar archivo .env (credenciales)")
    if not ENV_FILE.exists():
        ENV_TEMPLATE.write_text(TEMPLATE_ENV, encoding="utf-8")
        print(f"  {_YELLOW}{EMOJIS['alerta']} ALERTA: No existe taller-conexion-mongo/.env.{_RESET}")
        print(f"  {_YELLOW}{EMOJIS['alerta']} WARNING: Se generó datos de ejemplo en: {ENV_TEMPLATE.name}{_RESET}")
        print("  -> Copia .env.template a taller-conexion-mongo/.env, rellena MONGO_URI y vuelve a correr.")
        resumen(".env", False, "falta el archivo con credenciales; se creó .env.template.")
        return False
    uri = leer_env("MONGO_URI") or leer_env("mongo_uri")
    if not uri:
        print(f"  {_YELLOW}{EMOJIS['alerta']} ALERTA: .env existe pero MONGO_URI está vacía.{_RESET}")
        resumen(".env", False, "MONGO_URI vacía o sin credenciales.")
        return False
    resumen(".env", True, "presente y con MONGO_URI definida.")
    return True


# ── 6/7  Health Check MongoDB Atlas ─────────────────────────
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
    encabezado(6, 7, EMOJIS["health"], "Health Check: conexión a MongoDB Atlas")
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


# ── 7/7  Validación NUBE automática (Configuration as Code) ─
def validacion_nube():
    encabezado(7, 7, EMOJIS["nube"], "Validación NUBE en código (deploy_infra_nube.ps1 -> Terraform Atlas)")
    if not NUBE_SCRIPT.exists():
        resumen("Validación Nube", False, f"no existe {NUBE_SCRIPT.name}.")
        return False
    codigo = subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
         "-File", str(NUBE_SCRIPT)],
        cwd=ROOT,
    )
    return codigo.returncode == 0


# ── Ejecución ────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="Configuración como Código — Hyperflix / MongoDB Atlas")
    parser.add_argument(
        "--sin-nube",
        action="store_true",
        help="solo prepara el entorno local (omite la validación de nube con Terraform).",
    )
    args = parser.parse_args()

    banner()
    print("  Comando: ", " ".join(sys.argv))

    fase_python()
    fase_venv()
    fase_dependencias()
    fase_datalake()
    env_ok = fase_env()
    if env_ok:
        fase_health()

    faltas = [nombre for nombre, ok in RESULTADOS if not ok]
    print()
    print(f"  {_MAGENTA}╔═══════════════════════════════════════════════════════════════╗{_RESET}")
    print(f"  {_MAGENTA}║{_RESET}  {_BOLD}{_GREEN}RESUMEN FINAL{_RESET}  ·  revisa el estado de cada fase        {_MAGENTA}║{_RESET}")
    print(f"  {_MAGENTA}╚═══════════════════════════════════════════════════════════════╝{_RESET}")
    for nombre, ok in RESULTADOS:
        marca = f"{_GREEN}✔{_RESET}" if ok else f"{_RED}✘{_RESET}"
        print(f"    {marca}  {nombre}")
    barra_progreso(sum(1 for _, ok in RESULTADOS if ok), len(RESULTADOS) or 1)
    print("=" * 64)

    if not env_ok:
        print(f"\n  {_YELLOW}{EMOJIS['alerta']} FALTAN pasos:{_RESET} " + ", ".join(faltas))
        print(f"  {_YELLOW}Revisa el aviso del .env: crea .env.template ya generado, rellénalo y repite.{_RESET}")
        sys.exit(1)

    if faltas:
        print(f"  {_YELLOW}{EMOJIS['alerta']} Nota: falló '{', '.join(faltas)}', pero el .env es válido.{_RESET}")
        print(f"  {_YELLOW}       Igual se valida la nube; el exit code final lo reflejará.{_RESET}")

    print(f"\n  {_BOLD}{EMOJIS['ok']} ¡ENTORNO LISTO!{_RESET} Ejecutando de forma AUTOMÁTICA la validación de nube (Atlas) ...")
    if not args.sin_nube:
        if validacion_nube():
            print(f"\n  {_GREEN}★ Validación NUBE completada. Atlas queda sincronizado con el código (IaC). ★{_RESET}")
        else:
            print(f"\n  {_RED}✖ La validación NUBE falló. Revisa el log de deploy_infra_nube.ps1 (carpeta logs/).{_RESET}")
            sys.exit(1)
    else:
        print(f"  {_CYAN}(omitida con --sin-nube). Reproduce Atlas después con: .\\deploy_infra_nube.ps1{_RESET}")

    sys.exit(0 if not faltas else 1)


if __name__ == "__main__":
    main()