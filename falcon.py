"""
FALCON CFE — Lanzador principal.

Sistema de monitoreo de infraestructura eléctrica de CFE (Noroeste de México),
versión web con IA Astra integrada.

Flujo de inicio:
  1. Busca llama-server.exe (en llama-cpp/ o rutas conocidas)
     - Si no existe → pregunta si descargar (Recomendado)
  2. Busca un modelo .gguf disponible
     - Si no existe → pregunta si descargar (Recomendado)
  3. Arranca llama-server en puerto 8080 (background)
  4. Espera a que el servidor LLM esté listo
  5. Arranca el servidor web de FALCON (abre navegador)

Uso:
    python falcon.py
"""
from __future__ import annotations

import atexit
import os
import shutil
import subprocess
import sys
import time
import zipfile
from pathlib import Path

# Raíz del proyecto
RAIZ = Path(__file__).resolve().parent
LLAMA_DIR = RAIZ / "llama-cpp"
MODELS_DIR = LLAMA_DIR / "models"

# Rutas donde buscar llama-server.exe
RUTAS_LLAMA_SERVER = [
    LLAMA_DIR / "llama-server.exe",
    Path.home() / "Documents" / "astra" / "dist" / "llama-cpp" / "llama-server.exe",
    Path.home() / "Documents" / "ProyectoMEC" / "llama-cpp" / "llama-server.exe",
    Path.home() / "astra" / "dist" / "llama-cpp" / "llama-server.exe",
]

# Rutas donde buscar modelos .gguf
RUTAS_MODELOS = [
    MODELS_DIR,
    LLAMA_DIR,
    Path.home() / "Documents" / "astra" / "dist" / "llama-cpp" / "models",
    Path.home() / "Documents" / "astra" / "dist" / "llama-cpp",
    Path.home() / ".cache" / "lm-studio" / "models",
]

# URLs de descarga
LLAMA_CPP_VERSION = "b4552"
LLAMA_SERVER_URL = (
    f"https://github.com/ggerganov/llama.cpp/releases/download/{LLAMA_CPP_VERSION}/"
    f"llama-{LLAMA_CPP_VERSION}-bin-win-cpu-x64.zip"
)
MODELO_URL = "https://huggingface.co/Qwen/Qwen2.5-3B-Instruct-GGUF/resolve/main/qwen2.5-3b-instruct-q4_k_m.gguf"
MODELO_NOMBRE = "qwen2.5-3b-instruct-q4_k_m.gguf"

# Configuración del servidor LLM
LLAMA_PORT = 8080
LLAMA_CONTEXT = 2048
LLAMA_THREADS = 0  # 0 = auto-detectar

# Proceso del servidor LLM (global para poder matarlo al salir)
_llama_process: subprocess.Popen | None = None


def encontrar_llama_server() -> Path | None:
    """Busca llama-server.exe en rutas conocidas."""
    for ruta in RUTAS_LLAMA_SERVER:
        if ruta.exists():
            return ruta
    return None


def encontrar_modelo() -> Path | None:
    """Busca el primer .gguf disponible en rutas conocidas."""
    for ruta in RUTAS_MODELOS:
        if ruta.exists():
            if ruta.is_file() and ruta.suffix == ".gguf":
                return ruta
            modelos = sorted(ruta.glob("**/*.gguf"), key=lambda p: p.stat().st_size)
            if modelos:
                return modelos[0]
    return None


def _progreso_descarga(bloques, tam_bloque, tam_total):
    """Muestra barra de progreso para descargas."""
    descargado = bloques * tam_bloque
    if tam_total > 0:
        pct = min(100, descargado * 100 // tam_total)
        mb_desc = descargado / 1e6
        mb_total = tam_total / 1e6
        barra = "█" * (pct // 5) + "░" * (20 - pct // 5)
        print(f"\r     [{barra}] {pct}% ({mb_desc:.0f}/{mb_total:.0f} MB)", end="", flush=True)
    else:
        mb_desc = descargado / 1e6
        print(f"\r     Descargando... {mb_desc:.0f} MB", end="", flush=True)


def descargar_llama_server() -> Path | None:
    """Descarga llama-server.exe desde GitHub Releases."""
    import urllib.request

    LLAMA_DIR.mkdir(parents=True, exist_ok=True)
    destino_exe = LLAMA_DIR / "llama-server.exe"
    zip_path = LLAMA_DIR / "llama-cpp-download.zip"

    print(f"\n  📥 Descargando llama-server ({LLAMA_CPP_VERSION})...")
    print(f"     Fuente: github.com/ggerganov/llama.cpp")

    try:
        urllib.request.urlretrieve(LLAMA_SERVER_URL, str(zip_path), _progreso_descarga)
        print()  # Nueva línea después de la barra
    except Exception as e:
        print(f"\n  ❌ Error descargando: {e}")
        print(f"     Descarga manual: {LLAMA_SERVER_URL}")
        return None

    # Extraer llama-server.exe del ZIP
    print("  📦 Extrayendo...")
    try:
        with zipfile.ZipFile(str(zip_path), 'r') as zf:
            # Buscar llama-server.exe dentro del ZIP
            server_names = [n for n in zf.namelist()
                           if "llama-server" in n.lower() and n.endswith(".exe")]
            if not server_names:
                server_names = [n for n in zf.namelist()
                               if "server" in n.lower() and n.endswith(".exe")]

            if server_names:
                data = zf.read(server_names[0])
                destino_exe.write_bytes(data)

                # Extraer DLLs
                dlls = [n for n in zf.namelist() if n.endswith(".dll")]
                for dll in dlls:
                    dll_name = Path(dll).name
                    (LLAMA_DIR / dll_name).write_bytes(zf.read(dll))

                print(f"  ✓ llama-server.exe instalado ({destino_exe.stat().st_size / 1e6:.0f} MB)")
            else:
                print("  ❌ No se encontró llama-server.exe en el archivo")
                return None
    except Exception as e:
        print(f"  ❌ Error extrayendo: {e}")
        return None
    finally:
        if zip_path.exists():
            zip_path.unlink()

    return destino_exe


def descargar_modelo() -> Path | None:
    """Descarga el modelo Qwen2.5-3B recomendado desde HuggingFace."""
    import urllib.request

    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    destino = MODELS_DIR / MODELO_NOMBRE

    print(f"\n  📥 Descargando modelo: {MODELO_NOMBRE}")
    print(f"     Tamaño aprox: ~2.0 GB (puede tardar 3-8 minutos)")
    print(f"     Fuente: huggingface.co/Qwen")

    try:
        urllib.request.urlretrieve(MODELO_URL, str(destino), _progreso_descarga)
        print()  # Nueva línea después de la barra
        print(f"  ✓ Modelo instalado ({destino.stat().st_size / 1e9:.1f} GB)")
        return destino
    except Exception as e:
        print(f"\n  ❌ Error descargando modelo: {e}")
        print(f"     Descarga manual:")
        print(f"     {MODELO_URL}")
        print(f"     Colócalo en: {MODELS_DIR}/")
        if destino.exists():
            destino.unlink()  # Eliminar descarga incompleta
        return None


def detectar_threads() -> int:
    """Detecta número óptimo de threads para llama-server."""
    if LLAMA_THREADS > 0:
        return LLAMA_THREADS
    try:
        import psutil
        cores = psutil.cpu_count(logical=False) or 4
        return min(cores, 6)
    except ImportError:
        cores = os.cpu_count() or 4
        return min(cores // 2, 6)


def arrancar_llama_server(exe_path: Path, model_path: Path) -> bool:
    """Arranca llama-server.exe como proceso en background."""
    global _llama_process

    threads = detectar_threads()
    cmd = [
        str(exe_path),
        "-m", str(model_path),
        "-c", str(LLAMA_CONTEXT),
        "--port", str(LLAMA_PORT),
        "-t", str(threads),
        "--log-disable",
    ]

    print(f"\n  🧠 Modelo: {model_path.name} ({model_path.stat().st_size / 1e9:.1f} GB)")
    print(f"  ⚙️  Config: ctx={LLAMA_CONTEXT}, threads={threads}, port={LLAMA_PORT}")
    print(f"  🚀 Arrancando llama-server...")

    try:
        kwargs = {}
        if sys.platform == "win32":
            kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW

        _llama_process = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            **kwargs,
        )

        atexit.register(_matar_llama_server)
        return True
    except FileNotFoundError:
        print(f"  ❌ No se pudo ejecutar: {exe_path}")
        return False
    except Exception as e:
        print(f"  ❌ Error arrancando llama-server: {e}")
        return False


def esperar_llama_server(timeout: float = 30.0) -> bool:
    """Espera a que llama-server responda en el puerto 8080."""
    import urllib.request
    import urllib.error

    print(f"  ⏳ Esperando que llama-server esté listo (máx {timeout:.0f}s)...", end="", flush=True)
    inicio = time.time()
    intentos = 0

    while time.time() - inicio < timeout:
        if _llama_process and _llama_process.poll() is not None:
            print(f"\n  ❌ llama-server se detuvo (código: {_llama_process.returncode})")
            stderr = _llama_process.stderr.read().decode("utf-8", errors="ignore")[-500:]
            if stderr:
                print(f"     Error: {stderr}")
            return False

        try:
            req = urllib.request.Request(
                f"http://127.0.0.1:{LLAMA_PORT}/health",
                method="GET"
            )
            with urllib.request.urlopen(req, timeout=2) as resp:
                if resp.status == 200:
                    elapsed = time.time() - inicio
                    print(f" ✓ ({elapsed:.1f}s)")
                    return True
        except (urllib.error.URLError, OSError, TimeoutError):
            pass

        intentos += 1
        if intentos % 5 == 0:
            print(".", end="", flush=True)
        time.sleep(0.5)

    print(f"\n  ⚠️  Timeout ({timeout:.0f}s) esperando llama-server")
    return False


def _matar_llama_server():
    """Mata el proceso de llama-server al cerrar FALCON."""
    global _llama_process
    if _llama_process is not None:
        try:
            _llama_process.terminate()
            _llama_process.wait(timeout=5)
        except Exception:
            try:
                _llama_process.kill()
            except Exception:
                pass
        _llama_process = None


def verificar_puerto_ocupado() -> bool:
    """Verifica si ya hay algo en el puerto 8080 (quizás llama-server ya corre)."""
    import urllib.request
    import urllib.error

    try:
        req = urllib.request.Request(f"http://127.0.0.1:{LLAMA_PORT}/health")
        with urllib.request.urlopen(req, timeout=2) as resp:
            if resp.status == 200:
                return True
    except (urllib.error.URLError, OSError):
        pass
    return False


def preguntar_si_no(mensaje: str, recomendado_si: bool = True) -> bool:
    """
    Pregunta Sí/No al usuario.
    Si recomendado_si=True, la opción por defecto (Enter) es Sí.
    Muestra '(Recomendado)' en la opción sugerida.
    """
    if recomendado_si:
        opciones = "[S (Recomendado)/n]"
    else:
        opciones = "[s/N (Recomendado)]"

    try:
        resp = input(f"  {mensaje} {opciones}: ").strip().lower()
        if resp == "":
            return recomendado_si  # Enter = opción por defecto
        return resp in ("s", "si", "sí", "y", "yes")
    except (KeyboardInterrupt, EOFError):
        print()
        return recomendado_si  # Si interrumpe, asumir la recomendada


def main():
    print("=" * 60)
    print("  🦅 FALCON CFE — Sistema de Monitoreo + IA Astra")
    print("=" * 60)

    # === Paso 1: Verificar si llama-server ya está corriendo ===
    if verificar_puerto_ocupado():
        print(f"\n  ✓ llama-server ya corriendo en puerto {LLAMA_PORT}")
    else:
        # === Paso 2: Buscar o instalar llama-server.exe ===
        exe = encontrar_llama_server()

        if exe is None:
            print("\n  ⚠️  llama-server.exe no encontrado")
            print("     (Es el motor de inteligencia artificial de Astra)")
            print("")
            if preguntar_si_no("¿Descargar e instalar llama-server?", recomendado_si=True):
                exe = descargar_llama_server()
                if exe is None:
                    print("\n  Continuando sin IA... (Astra responderá con datos básicos)")
            else:
                print("\n  OK. Astra funcionará con respuestas básicas (sin IA generativa).")
        else:
            print(f"\n  ✓ llama-server: {exe}")

        # === Paso 3: Buscar o instalar modelo .gguf ===
        if exe is not None:
            modelo = encontrar_modelo()

            if modelo is None:
                print("\n  ⚠️  No se encontró ningún modelo de IA (.gguf)")
                print("     (El modelo es el cerebro de Astra — Qwen2.5 3B recomendado)")
                print("")
                if preguntar_si_no("¿Descargar modelo Qwen2.5-3B? (~2 GB)", recomendado_si=True):
                    modelo = descargar_modelo()
                    if modelo is None:
                        print("\n  Continuando sin modelo... (Astra responderá con datos básicos)")
                else:
                    print("\n  OK. Astra funcionará con respuestas básicas (sin IA generativa).")
            else:
                print(f"  ✓ Modelo: {modelo.name} ({modelo.stat().st_size / 1e9:.1f} GB)")

            # === Paso 4: Arrancar llama-server ===
            if modelo is not None:
                if not arrancar_llama_server(exe, modelo):
                    print("  ⚠️  No se pudo arrancar llama-server")
                    print("     Astra responderá con datos básicos del sistema.")
                else:
                    # === Paso 5: Esperar a que esté listo ===
                    if not esperar_llama_server(timeout=45):
                        print("  ⚠️  llama-server no respondió a tiempo")
                        print("     Se reconectará cuando esté listo...")

    # === Paso 6: Arrancar servidor web FALCON ===
    print("")
    from palantir_web.servidor import main as web_main
    web_main()


if __name__ == "__main__":
    main()
