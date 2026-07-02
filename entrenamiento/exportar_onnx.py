"""
Exportador de modelo a ONNX — Palantir CFE.

Convierte un modelo YOLO entrenado (.pt) a formato ONNX, que es el que
consume el motor de detección del dashboard (deteccion_ia.py -> DetectorONNX).

Uso:
    python entrenamiento/exportar_onnx.py --pesos runs/detect/cfe_satelital/weights/best.pt
"""
from __future__ import annotations

import argparse
from pathlib import Path


def exportar(pesos: str, imgsz: int):
    try:
        from ultralytics import YOLO
    except ImportError:
        print("❌ ultralytics no instalado. Ejecuta: pip install ultralytics")
        return

    ruta = Path(pesos)
    if not ruta.exists():
        print(f"❌ No existe el archivo de pesos: {ruta}")
        return

    print(f"📦 Exportando {ruta.name} a ONNX (imgsz={imgsz})...")
    model = YOLO(str(ruta))
    onnx_path = model.export(format="onnx", imgsz=imgsz, opset=12, simplify=True)
    print(f"✅ Exportado: {onnx_path}")
    print(f"\nÚsalo en el dashboard:")
    print(f"   export PALANTIR_MODELO_ONNX={onnx_path}")
    print(f"   python -m palantir_cfe")


def main():
    ap = argparse.ArgumentParser(description="Exporta un modelo YOLO .pt a ONNX")
    ap.add_argument("--pesos", required=True, help="Ruta al archivo best.pt")
    ap.add_argument("--imgsz", type=int, default=640)
    args = ap.parse_args()
    exportar(args.pesos, args.imgsz)


if __name__ == "__main__":
    main()
