# 🎓 Pipeline de Entrenamiento — Detección Satelital CFE

Guía completa para entrenar el modelo de IA que detecta las **24 clases** de
infraestructura de CFE en imágenes satelitales.

## 🧠 ¿Qué modelo usar? (Recomendación)

Para detección de objetos en imágenes satelitales, la mejor opción práctica es:

### ✅ Recomendado: **YOLOv8m** (o **YOLOv11m**)
- **Por qué:** Excelente balance precisión/velocidad, detección en tiempo real,
  fácil de entrenar, exporta a ONNX (lo que consume el dashboard), gran comunidad.
- **YOLOv8m** = versión "medium", ideal para el detalle de estructuras satelitales.
- **YOLOv11m** = generación más nueva, ~mejor precisión con cómputo similar.

### Comparativa de variantes

| Modelo | Params | Velocidad | Precisión | Cuándo usar |
|--------|--------|-----------|-----------|-------------|
| YOLOv8n | 3M | ⚡⚡⚡ | ⭐⭐ | Pruebas rápidas, CPU |
| YOLOv8s | 11M | ⚡⚡ | ⭐⭐⭐ | GPU modesta |
| **YOLOv8m** | 26M | ⚡ | ⭐⭐⭐⭐ | **Recomendado** |
| YOLOv8l | 44M | 🐢 | ⭐⭐⭐⭐⭐ | Máxima precisión, GPU potente |
| YOLOv11m | 20M | ⚡ | ⭐⭐⭐⭐⭐ | Última generación |

### Alternativas especializadas en satélite (avanzado)
- **YOLOv8-OBB** (Oriented Bounding Boxes): útil porque las estructuras satelitales
  tienen orientaciones arbitrarias. Detecta cajas rotadas.
- **[Ultralytics + SAHI](https://github.com/obss/sahi):** "Slicing Aided Hyper Inference" —
  parte la imagen en mosaicos para detectar objetos pequeños (torres, postes, medidores).
  **Muy recomendado** para activos chicos en imágenes grandes.
- **DOTA / DIOR pretrained:** datasets de teledetección; puedes hacer transfer learning.

## 📋 Flujo completo (5 pasos)

### Paso 1 — Generar la configuración del dataset
```bash
python entrenamiento/generar_config.py
```
Crea `dataset.yaml` con las 24 clases (sincronizado con el catálogo).

### Paso 2 — Descargar imágenes satelitales base
```bash
pip install pillow httpx
python entrenamiento/descargar_imagenes.py --zoom 18 --radio 400
```
Descarga recortes de las ubicaciones conocidas de CFE a `datos/raw/`.
Cada imagen trae su archivo `.txt` con la georreferencia (para reconvertir cajas
a coordenadas después).

### Paso 3 — Etiquetar (bounding boxes)
Sube las imágenes a una herramienta de etiquetado y dibuja las cajas con las 24
clases. Herramientas recomendadas:
- **[Roboflow](https://roboflow.com)** — la más fácil, exporta directo a formato YOLO
- **[CVAT](https://cvat.ai)** — potente, open source
- **LabelImg** — sencillo, local

Exporta en **formato YOLO** y organiza así:
```
datos/
├── images/
│   ├── train/   (70% de las imágenes)
│   ├── val/     (20%)
│   └── test/    (10%)
└── labels/
    ├── train/   (un .txt por imagen: clase cx cy w h normalizados)
    ├── val/
    └── test/
```

> 💡 **Consejo:** empieza con las clases más fáciles y numerosas (subestaciones,
> torres grandes, plantas solares, aerogeneradores). Necesitas ~100-300 ejemplos
> por clase para resultados decentes; más para las clases difíciles (medidores, cajeros).

### Paso 4 — Entrenar
```bash
pip install ultralytics
python entrenamiento/entrenar.py --modelo yolov8m.pt --epochs 100 --imgsz 640
```
Al terminar, exporta automáticamente a ONNX. Usa `--device cpu` si no tienes GPU.

### Paso 5 — Conectar al dashboard
```bash
export PALANTIR_MODELO_ONNX=runs/detect/cfe_satelital/weights/best.onnx
python -m palantir_cfe
```
Abre la pestaña 🛰️ SATÉLITE — ahora usa tu modelo real.

## 🛰️ Consejos para imágenes satelitales

- **Zoom 17-19** da la mejor resolución para estructuras (0.3-1 m/pixel).
- Las estructuras satelitales **no tienen orientación fija**: por eso el entrenamiento
  usa rotaciones completas (`degrees=180`) y flip vertical.
- Para **objetos chicos** (postes, medidores, transformadores), usa **SAHI** en inferencia
  o entrena con `imgsz` alto (1024).
- Combina imágenes de **Esri** y **Google Satellite** para más variedad.

## 📂 Archivos de este pipeline

| Archivo | Función |
|---------|---------|
| `generar_config.py` | Genera `dataset.yaml` desde el catálogo (24 clases) |
| `descargar_imagenes.py` | Descarga recortes satelitales de ubicaciones CFE |
| `entrenar.py` | Entrena YOLOv8/v11 y exporta a ONNX |
| `exportar_onnx.py` | Convierte un `.pt` entrenado a ONNX |
| `dataset.yaml` | Configuración del dataset (autogenerada) |
