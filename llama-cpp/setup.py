"""
llama-cpp/setup.py — Descarga y configura llama-server para FALCON.

Descarga automáticamente llama-server.exe (Windows) desde GitHub Releases.
Si ya existe localmente (en astra/dist/llama-cpp/), lo copia de ahí.

Uso:
    python llama-cpp/setup.py

Después de ejecutar:
    - llama-cpp/llama-server.exe estará listo
    - falcon.py lo arrancará automáticamente
"""
from __future__ import annotations

import os
import shutil
import sys
import zipfile
from pathlib import Path

# Versión de llama.cpp a descargar
LLAMA_CPP_VERSION = "b4552"
RELEASE_URL = (
    f"https://github.com/ggerganov/llama.cpp/releases/download/{LLAMA_CPP_VERSION}/"
    f"llama-{LLAMA_CPP_VERSION}-bin-win-cpu-x64.zip"
)

# Rutas
SCRIPT_DIR = Path(__file__).resolve().parent
LLAMA_SERVER_EXE = SCRIPT_DIR / "llama-server.exe"
MODELS_DIR = SCRIPT_DIR / "models"

# Rutas alternativas donde puede estar llama-server ya descargado
RUTAS_ALTERNATIVAS = [
    Path.home() / "Documents" / "astra" / "dist" / "llama-cpp" / "llama-server.exe",
    Path.home() / "astra" / "dist" / "llama-cpp" / "llama-server.exe",
    Path.home() / "Documents" / "ProyectoMEC" / "dist" / "llama-cpp" / "llama-server.exe",
]


def encontrar_local() -> Path | None:
    """Busca llama-server.exe en rutas conocidas."""
    for ruta in RUTAS_ALTERNATIVAS:
        if ruta.exists():
            return ruta
    return None


def descargar_llama_server():
    """Descarga llama-server.exe desde GitHub Releases."""
    import urllib.request
    import tempfile

    print(f"📥 Descargando llama.cpp {LLAMA_CPP_VERSION}...")
    print(f"   URL: {RELEASE_URL}")
    print(f"   Esto puede tardar unos minutos...")

    zip_path = SCRIPT_DIR / "llama-cpp-download.zip"
    try:
        urllib.request.urlretrieve(RELEASE_URL, str(zip_path))
    except Exception as e:
        print(f"\n❌ Error descargando: {e}")
        print("\n💡 Alternativas:")
        print("   1. Descarga manualmente desde: https://github.com/ggerganov/llama.cpp/releases")
        print("   2. Busca el archivo 'llama-*-bin-win-cpu-x64.zip'")
        print(f"   3. Extrae llama-server.exe en: {SCRIPT_DIR}")
        return False

    # Extraer llama-server.exe del ZIP
    print("📦 Extrayendo llama-server.exe...")
    try:
        with zipfile.ZipFile(str(zip_path), 'r') as zf:
            # Buscar llama-server.exe dentro del ZIP
            server_names = [n for n in zf.namelist() if "llama-server" in n.lower() and n.endswith(".exe")]
            if not server_names:
                # Puede estar como "server.exe" en versiones antiguas
                server_names = [n for n in zf.namelist() if "server" in n.lower() and n.endswith(".exe")]

            if server_names:
                # Extraer el exe
                source = server_names[0]
                data = zf.read(source)
                LLAMA_SERVER_EXE.write_bytes(data)
                print(f"   ✓ Extraído: {source} → {LLAMA_SERVER_EXE.name}")

                # También extraer DLLs necesarias
                dlls = [n for n in zf.namelist() if n.endswith(".dll")]
                for dll in dlls:
                    dll_name = Path(dll).name
                    (SCRIPT_DIR / dll_name).write_bytes(zf.read(dll))
                if dlls:
                    print(f"   ✓ {len(dlls)} DLLs extraídas")
            else:
                print("❌ No se encontró llama-server.exe en el ZIP")
                return False
    except Exception as e:
        print(f"❌ Error extrayendo: {e}")
        return False
    finally:
        # Limpiar ZIP
        if zip_path.exists():
            zip_path.unlink()

    return True


def verificar_modelo() -> Path | None:
    """Busca un modelo .gguf disponible."""
    # Buscar en la carpeta models/
    MODELS_DIR.mkdir(exist_ok=True)

    modelos_aqui = list(MODELS_DIR.glob("*.gguf"))
    if modelos_aqui:
        return modelos_aqui[0]

    # Buscar en rutas del usuario
    rutas_modelo = [
        Path.home() / "Documents" / "astra" / "dist" / "llama-cpp" / "models",
        Path.home() / "Documents" / "astra" / "dist" / "llama-cpp",
        Path.home() / ".cache" / "lm-studio" / "models",
        Path.home() / "Documents" / "ProyectoMEC" / "modelos",
    ]

    for ruta in rutas_modelo:
        if ruta.exists():
            modelos = list(ruta.glob("**/*.gguf"))
            if modelos:
                return modelos[0]

    return None


def selector_modelos():
    """Muestra opciones para descargar un modelo si no hay ninguno."""
    print("\n" + "=" * 60)
    print("  🧠 SELECTOR DE MODELOS — FALCON/Astra")
    print("=" * 60)

    modelo = verificar_modelo()
    if modelo:
        print(f"\n  ✓ Modelo encontrado: {modelo.name}")
        print(f"    Ruta: {modelo}")
        return modelo

    print("\n  ⚠️  No se encontró ningún modelo .gguf")
    print("\n  Modelos recomendados para tu PC (7.2 GB RAM, sin GPU):")
    print("")
    print("  [1] Qwen2.5-Coder-3B-Instruct (Q4_K_M) — 2.0 GB")
    print("      Mejor para código y respuestas técnicas")
    print("      URL: https://huggingface.co/bartowski/Qwen2.5-Coder-3B-Instruct-GGUF")
    print("")
    print("  [2] Qwen2.5-3B-Instruct (Q4_K_M) — 2.0 GB")
    print("      Buen balance general")
    print("      URL: https://huggingface.co/Qwen/Qwen2.5-3B-Instruct-GGUF")
    print("")
    print("  [3] Phi-3-mini-4k-instruct (Q4_K_M) — 2.3 GB")
    print("      Microsoft, rápido en CPU")
    print("      URL: https://huggingface.co/bartowski/Phi-3-mini-4k-instruct-GGUF")
    print("")

    MODELOS_DESCARGA = {
        "1": {
            "nombre": "qwen2.5-coder-3b-instruct-q4_k_m.gguf",
            "url": "https://huggingface.co/bartowski/Qwen2.5-Coder-3B-Instruct-GGUF/resolve/main/Qwen2.5-Coder-3B-Instruct-Q4_K_M.gguf",
        },
        "2": {
            "nombre": "qwen2.5-3b-instruct-q4_k_m.gguf",
            "url": "https://huggingface.co/Qwen/Qwen2.5-3B-Instruct-GGUF/resolve/main/qwen2.5-3b-instruct-q4_k_m.gguf",
        },
        "3": {
            "nombre": "phi-3-mini-4k-instruct-q4_k_m.gguf",
            "url": "https://huggingface.co/bartowski/Phi-3-mini-4k-instruct-GGUF/resolve/main/Phi-3-mini-4k-instruct-Q4_K_M.gguf",
        },
    }

    print("  [M] Ya tengo un modelo — indicar ruta manualmente")
    print("  [S] Salir sin descargar")
    print("")

    opcion = input("  Elige (1/2/3/M/S): ").strip().upper()

    if opcion == "S":
        print("\n  Puedes colocar un archivo .gguf en:")
        print(f"    {MODELS_DIR}/")
        return None

    if opcion == "M":
        ruta = input("  Ruta completa al .gguf: ").strip().strip('"')
        p = Path(ruta)
        if p.exists() and p.suffix == ".gguf":
            # Crear symlink o copiar
            destino = MODELS_DIR / p.name
            if not destino.exists():
                # Intentar symlink primero, si falla copiar
                try:
                    destino.symlink_to(p)
                    print(f"  ✓ Enlace creado: {destino.name} → {p}")
                except OSError:
                    print(f"  Copiando modelo ({p.stat().st_size / 1e9:.1f} GB)...")
                    shutil.copy2(str(p), str(destino))
                    print(f"  ✓ Copiado: {destino}")
            return destino
        else:
            print(f"  ❌ No se encontró: {ruta}")
            return None

    if opcion in MODELOS_DESCARGA:
        modelo_info = MODELOS_DESCARGA[opcion]
        destino = MODELS_DIR / modelo_info["nombre"]
        print(f"\n  📥 Descargando {modelo_info['nombre']}...")
        print(f"      URL: {modelo_info['url']}")
        print(f"      Esto puede tardar varios minutos...")
        try:
            import urllib.request
            urllib.request.urlretrieve(modelo_info["url"], str(destino))
            print(f"  ✓ Descargado: {destino}")
            return destino
        except Exception as e:
            print(f"  ❌ Error: {e}")
            print(f"  Descárgalo manualmente y colócalo en: {MODELS_DIR}/")
            return None

    print("  Opción no reconocida.")
    return None


def main():
    print("=" * 60)
    print("  🦅 FALCON — Configuración de llama-server")
    print("=" * 60)

    # Paso 1: Verificar/obtener llama-server.exe
    if LLAMA_SERVER_EXE.exists():
        print(f"\n  ✓ llama-server.exe ya existe ({LLAMA_SERVER_EXE.stat().st_size / 1e6:.1f} MB)")
    else:
        # Buscar copia local
        local = encontrar_local()
        if local:
            print(f"\n  📋 Encontrado en: {local}")
            print(f"     Copiando a {SCRIPT_DIR}...")
            shutil.copy2(str(local), str(LLAMA_SERVER_EXE))
            # También copiar DLLs si las hay
            for dll in local.parent.glob("*.dll"):
                shutil.copy2(str(dll), str(SCRIPT_DIR / dll.name))
            print(f"  ✓ Copiado exitosamente")
        else:
            print("\n  ⚠️  llama-server.exe no encontrado")
            print("     Intentando descargar desde GitHub...")
            if not descargar_llama_server():
                print("\n  ❌ No se pudo obtener llama-server.exe")
                print(f"     Colócalo manualmente en: {SCRIPT_DIR}")
                sys.exit(1)

    # Paso 2: Verificar/obtener modelo
    modelo = selector_modelos()

    print("\n" + "=" * 60)
    if LLAMA_SERVER_EXE.exists():
        print("  ✓ llama-server.exe: LISTO")
    if modelo:
        print(f"  ✓ Modelo: {modelo.name}")
        print(f"\n  🚀 Todo listo. Ejecuta: python falcon.py")
    else:
        print("  ⚠️  Sin modelo — coloca un .gguf en llama-cpp/models/")
    print("=" * 60)


if __name__ == "__main__":
    main()
