"""
FALCON CFE — Lanzador principal.

Sistema de monitoreo de infraestructura eléctrica de CFE (Noroeste de México),
versión web con IA Astra integrada.

Flujo de inicio:
  1. Busca llama-server.exe (en llama-cpp/ o rutas conocidas)
  2. Busca un modelo .gguf disponible
  3. Arranca llama-server en puerto 8080 (background)
  4. Espera a que el servidor LLM esté listo
  5. Arranca el servidor web de FALCON (abre navegador)

Si no encuentra llama-server o modelo, ejecuta el selector interactivo.

Uso:
    python falcon.py
"""
from __future__ import annotations

import atexit
import os
import subprocess
import sys
import time
from pathlib import Path

# Raíz del proyecto
RAIZ = Path(__file__).resolve().parent
LLAMA_DIR = RAIZ / "llama-cpp"
MODELS_DIR = LLAMA_DIR / "models"

# Rutas donde buscar llama-server.exe
RUTAS_LLAMA_SERVER = [
    LLAMA_DIR / "llama-server.exe",
    Path.home() / "Documents" / "astra" / "dist" / "llama-cpp" / "llama-server.exe",
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


def detectar_threads() -> int:
    """Detecta número óptimo de threads para llama-server."""
    if LLAMA_THREADS > 0:
        return LLAMA_THREADS
    try:
        import psutil
        # Usar cores físicos (no hyperthreading) para mejor rendimiento
        cores = psutil.cpu_count(logical=False) or 4
        return min(cores, 6)  # Máximo 6 para no saturar el sistema
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
        "--log-disable",  # No llenar la terminal con logs del LLM
    ]

    print(f"  🧠 Modelo: {model_path.name} ({model_path.stat().st_size / 1e9:.1f} GB)")
    print(f"  ⚙️  Config: ctx={LLAMA_CONTEXT}, threads={threads}, port={LLAMA_PORT}")
    print(f"  🚀 Arrancando llama-server...")

    try:
        # Ejecutar en background sin mostrar ventana (Windows)
        kwargs = {}
        if sys.platform == "win32":
            # CREATE_NO_WINDOW para que no abra cmd.exe
            kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW

        _llama_process = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            **kwargs,
        )

        # Registrar cleanup al salir
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
        # Verificar que el proceso sigue vivo
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


def main():
    print("=" * 60)
    print("  🦅 FALCON CFE — Sistema de Monitoreo + IA Astra")
    print("=" * 60)

    # === Paso 1: Verificar si llama-server ya está corriendo ===
    if verificar_puerto_ocupado():
        print(f"\n  ✓ llama-server ya está corriendo en puerto {LLAMA_PORT}")
    else:
        # === Paso 2: Buscar llama-server.exe ===
        exe = encontrar_llama_server()
        if exe is None:
            print("\n  ⚠️  llama-server.exe no encontrado")
            print("     Ejecuta primero: python llama-cpp/setup.py")
            print("")
            print("  ¿Continuar sin LLM? (Astra usará modo reglas)")
            try:
                resp = input("  [S/n]: ").strip().lower()
                if resp == "n":
                    sys.exit(1)
            except (KeyboardInterrupt, EOFError):
                sys.exit(0)
        else:
            print(f"\n  ✓ llama-server: {exe}")

            # === Paso 3: Buscar modelo .gguf ===
            modelo = encontrar_modelo()
            if modelo is None:
                print("  ⚠️  No se encontró ningún modelo .gguf")
                print("     Ejecuta: python llama-cpp/setup.py")
                print("")
                print("  ¿Continuar sin LLM? (Astra usará modo reglas)")
                try:
                    resp = input("  [S/n]: ").strip().lower()
                    if resp == "n":
                        sys.exit(1)
                except (KeyboardInterrupt, EOFError):
                    sys.exit(0)
            else:
                # === Paso 4: Arrancar llama-server ===
                if not arrancar_llama_server(exe, modelo):
                    print("  ⚠️  No se pudo arrancar llama-server")
                    print("     Continuando sin LLM...")
                else:
                    # === Paso 5: Esperar a que esté listo ===
                    if not esperar_llama_server(timeout=45):
                        print("  ⚠️  llama-server no respondió a tiempo")
                        print("     Continuando... (se reconectará cuando esté listo)")

    # === Paso 6: Arrancar servidor web FALCON ===
    print("")
    from palantir_web.servidor import main as web_main
    web_main()


if __name__ == "__main__":
    main()
