"""
Entrenamiento del modelo de detección satelital CFE — Palantir CFE.

Entrena un modelo YOLOv8/YOLOv11 con el dataset etiquetado de infraestructura
de CFE. Al terminar, exporta automáticamente a ONNX para usarlo en el dashboard.

Requisitos:
    pip install ultralytics

Uso básico:
    python entrenamiento/entrenar.py

Uso avanzado:
    python entrenamiento/entrenar.py --modelo yolov8m.pt --epochs 150 --imgsz 640 --batch 16

Modelos base recomendados (de menor a mayor precisión / cómputo):
    yolov8n.pt   nano    — rápido, para probar. ~3M parámetros
    yolov8s.pt   small   — buen balance en CPU/GPU modesta
    yolov8m.pt   medium  — RECOMENDADO para satélite (buen detalle)
    yolov8l.pt   large   — más preciso, necesita GPU
    yolo11m.pt   YOLOv11 — última generación, mejor precisión aún
"""
from __future__ import annotations

import argparse
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
DATASET = RAIZ / "dataset.yaml"


def entrenar(modelo: str, epochs: int, imgsz: int, batch: int, nombre: str,
             device: str, project: str | None = None, resume: bool = False):
    try:
        from ultralytics import YOLO
    except ImportError:
        print("❌ ultralytics no instalado. Ejecuta: pip install ultralytics")
        return

    if not DATASET.exists():
        print(f"❌ No existe {DATASET}. Ejecuta primero: python entrenamiento/generar_config.py")
        return

    # Reanudar un entrenamiento interrumpido (ej. si Colab se desconectó)
    if resume and project:
        last = Path(project) / nombre / "weights" / "last.pt"
        if last.exists():
            print(f"🔄 Reanudando entrenamiento desde {last}")
            model = YOLO(str(last))
            resultados = model.train(resume=True)
            _exportar_onnx(resultados, imgsz)
            return
        print(f"⚠️ No hay checkpoint para reanudar en {last}. Empezando de cero.")

    print(f"🚀 Entrenando {modelo} sobre {DATASET.name}")
    print(f"   epochs={epochs}, imgsz={imgsz}, batch={batch}, device={device}, project={project}")

    model = YOLO(modelo)
    kwargs = dict(
        data=str(DATASET), epochs=epochs, imgsz=imgsz, batch=batch,
        device=device, name=nombre, patience=30,
        save_period=10,        # guarda un checkpoint cada 10 épocas (para reanudar)
        # Augmentaciones útiles para vista satelital (cenital, sin arriba/abajo fijo):
        degrees=180, fliplr=0.5, flipud=0.5, mosaic=1.0, scale=0.5,
        hsv_h=0.015, hsv_s=0.7, hsv_v=0.4,
    )
    if project:
        kwargs["project"] = project   # guardar en carpeta (ej. Google Drive)
    resultados = model.train(**kwargs)
    print("✅ Entrenamiento terminado.")
    _exportar_onnx(resultados, imgsz)


def _exportar_onnx(resultados, imgsz):
    """Exporta el mejor modelo a ONNX."""
    from ultralytics import YOLO

    # Exportar a ONNX automáticamente
    print("📦 Exportando mejor modelo a ONNX...")
    best = Path(resultados.save_dir) / "weights" / "best.pt"
    if best.exists():
        m = YOLO(str(best))
        onnx_path = m.export(format="onnx", imgsz=imgsz, opset=12, simplify=True)
        print(f"✅ Modelo ONNX exportado: {onnx_path}")
        print(f"\nPara usarlo en el dashboard:")
        print(f"   export PALANTIR_MODELO_ONNX={onnx_path}")
        print(f"   python -m palantir_cfe")
    else:
        print(f"⚠️ No se encontró best.pt en {best.parent}")


def main():
    ap = argparse.ArgumentParser(description="Entrena el detector satelital CFE")
    ap.add_argument("--modelo", default="yolov8m.pt", help="Modelo base (yolov8m.pt recomendado)")
    ap.add_argument("--epochs", type=int, default=100)
    ap.add_argument("--imgsz", type=int, default=960,
                    help="Resolución. 960 detecta mejor objetos chicos (torres, postes)")
    ap.add_argument("--batch", type=int, default=-1,
                    help="-1 = automático (ajusta al tamaño de la GPU y evita quedarse sin memoria)")
    ap.add_argument("--nombre", default="cfe_satelital")
    ap.add_argument("--device", default="0", help="'0' para GPU, 'cpu' para CPU")
    ap.add_argument("--project", default=None,
                    help="Carpeta donde guardar (ej. Google Drive para no perder el progreso)")
    ap.add_argument("--resume", action="store_true",
                    help="Reanudar un entrenamiento interrumpido (usa el último checkpoint)")
    args = ap.parse_args()
    entrenar(args.modelo, args.epochs, args.imgsz, args.batch, args.nombre,
             args.device, args.project, args.resume)


if __name__ == "__main__":
    main()
