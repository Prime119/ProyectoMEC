"""
Generador de configuración de dataset para entrenamiento YOLO — Palantir CFE.

Lee las clases desde palantir_cfe/catalogo_activos.py y genera el archivo
`dataset.yaml` que consume el entrenamiento de YOLOv8/YOLOv11.

Así, el dataset SIEMPRE queda sincronizado con el catálogo: si agregas una clase
nueva al catálogo (como los postes), solo vuelves a correr este script.

Uso:
    python entrenamiento/generar_config.py
"""
from __future__ import annotations

import sys
from pathlib import Path

# Permitir importar el paquete palantir_cfe
RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from palantir_cfe.catalogo_activos import CLASES_ORDENADAS, CATALOGO, NUM_CLASES


def generar_dataset_yaml(ruta_dataset: str = "./datos") -> str:
    """Genera el contenido del dataset.yaml para YOLO."""
    lineas = [
        "# ===================================================================",
        "# Dataset CFE — Detección satelital de infraestructura",
        "# GENERADO AUTOMÁTICAMENTE desde palantir_cfe/catalogo_activos.py",
        "# No editar a mano — vuelve a correr: python entrenamiento/generar_config.py",
        "# ===================================================================",
        "",
        f"path: {ruta_dataset}   # raíz del dataset",
        "train: images/train      # imágenes de entrenamiento (relativo a path)",
        "val: images/val          # imágenes de validación",
        "test: images/test        # imágenes de prueba (opcional)",
        "",
        f"nc: {NUM_CLASES}   # número de clases",
        "",
        "# Nombres de clases (el ÍNDICE debe coincidir con el catálogo)",
        "names:",
    ]
    for i, cid in enumerate(CLASES_ORDENADAS):
        nombre = CATALOGO[cid].nombre
        lineas.append(f"  {i}: {cid}   # {nombre}")
    return "\n".join(lineas) + "\n"


def main():
    contenido = generar_dataset_yaml()
    salida = Path(__file__).resolve().parent / "dataset.yaml"
    salida.write_text(contenido, encoding="utf-8")
    print(f"✅ dataset.yaml generado con {NUM_CLASES} clases en: {salida}")
    print("\nClases:")
    for i, cid in enumerate(CLASES_ORDENADAS):
        print(f"  {i:2d}  {cid:20s}  {CATALOGO[cid].nombre}")


if __name__ == "__main__":
    main()
