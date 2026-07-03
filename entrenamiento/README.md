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

## ⭐ El truco clave: AUTO-ETIQUETADO desde OpenStreetMap

Etiquetar miles de imágenes a mano es lo más caro de un proyecto de visión. Aquí lo
evitamos: **ya tenemos las coordenadas reales** de la infraestructura en OSM y en la
base de datos de CFE. El script `preparar_dataset.py` descarga la imagen satelital de
cada zona y **genera las etiquetas YOLO automáticamente** proyectando esas coordenadas
sobre la imagen. Esto se llama *supervisión débil* y te da un primer dataset funcional
en minutos, sin dibujar una sola caja.

## 📋 Flujo completo (4 pasos)

### Paso 1 — Generar dataset auto-etiquetado (OSM + satélite)
```bash
pip install pillow httpx
python entrenamiento/preparar_dataset.py --zoom 18 --radio 200 --max-imagenes 400
```
Descarga imágenes de 10 ciudades del Noroeste y crea automáticamente:
```
datos/
├── images/{train,val,test}/   imágenes satelitales
└── labels/{train,val,test}/   etiquetas YOLO (clase cx cy w h)
```
Cada etiqueta sale de proyectar la lat/lon real del activo sobre la imagen.

### Paso 2 — Generar la configuración del dataset
```bash
python entrenamiento/generar_config.py
```
Crea `dataset.yaml` con las 24 clases (sincronizado con el catálogo).

### Paso 3 — (Opcional pero recomendado) Revisar etiquetas
Las etiquetas automáticas son **aproximadas** (dependen de la precisión de OSM y del
tamaño estimado por clase). Para subir la calidad, abre `datos/` en
[Roboflow](https://roboflow.com), [CVAT](https://cvat.ai) o LabelImg y **corrige/afina**
las cajas. Con revisar unos cientos ya mejora bastante. Puedes entrenar sin este paso
para un primer modelo.

### Paso 4 — Entrenar y conectar
```bash
pip install ultralytics
python entrenamiento/entrenar.py --modelo yolov8m.pt --epochs 100 --imgsz 640
```
Al terminar exporta a ONNX automáticamente. Luego conéctalo al sistema:

**Windows (CMD):**
```cmd
set PALANTIR_MODELO_ONNX=runs\detect\cfe_satelital\weights\best.onnx
python falcon.py
```

**Windows (PowerShell):**
```powershell
$env:PALANTIR_MODELO_ONNX="runs\detect\cfe_satelital\weights\best.onnx"
python falcon.py
```

**Linux / Mac:**
```bash
export PALANTIR_MODELO_ONNX=runs/detect/cfe_satelital/weights/best.onnx
python falcon.py
```

## 🔁 Ciclo de mejora continua

1. Entrena un primer modelo con las etiquetas automáticas de OSM.
2. Corre el modelo sobre zonas donde OSM **no** tiene datos → detecta activos nuevos.
3. Revisa/corrige esas detecciones y agrégalas al dataset.
4. Reentrena. Cada vuelta el modelo detecta mejor lo que OSM no tenía.

Así el modelo termina cubriendo lo que ni OSM ni la base de datos tenían — que era
justo el objetivo (postes, medidores, oficinas, almacenes en todo el territorio).

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
| **`preparar_dataset.py`** | **Auto-etiqueta el dataset desde OSM + satélite (paso 1)** |
| `generar_config.py` | Genera `dataset.yaml` desde el catálogo (24 clases) |
| `descargar_imagenes.py` | (Alternativa) descarga recortes sin etiquetar |
| `entrenar.py` | Entrena YOLOv8/v11 y exporta a ONNX |
| `exportar_onnx.py` | Convierte un `.pt` entrenado a ONNX |
| `dataset.yaml` | Configuración del dataset (autogenerada) |

## ☁️ Entrenar en Google Colab (GPU gratis) — RECOMENDADO

Si no tienes GPU en tu PC, usa el notebook `FALCON_Colab.ipynb` para entrenar en la
nube con la GPU gratuita de Google:

1. Ve a [colab.research.google.com](https://colab.research.google.com)
2. **Archivo → Subir notebook** → sube `entrenamiento/FALCON_Colab.ipynb`
   (o **Archivo → Abrir → GitHub** y pega la URL del repo)
3. **Entorno de ejecución → Cambiar tipo** → Acelerador **GPU (T4)** → Guardar
4. Corre las celdas en orden (▶). El notebook:
   - Clona el repo e instala todo
   - Prepara hasta **2000 imágenes** auto-etiquetadas
   - Entrena YOLOv8m con GPU (~1-2 h)
   - Te **descarga el `cfe_satelital.onnx`** listo para conectar

5. En tu PC, conecta el modelo descargado:
   ```cmd
   set PALANTIR_MODELO_ONNX=C:\ruta\a\cfe_satelital.onnx
   python falcon.py
   ```

## ⚠️ Expectativas honestas

- El auto-etiquetado te da un **primer modelo funcional rápido**, pero su calidad
  depende de qué tan bien esté mapeado OSM y de que el tamaño estimado por clase
  sea correcto. No esperes precisión perfecta en la primera vuelta.
- Las clases con muchos ejemplos en OSM (subestaciones, torres, aerogeneradores,
  plantas) saldrán bien. Las que OSM casi no tiene (medidores, cajeros, oficinas,
  almacenes) necesitarán etiquetado manual o el ciclo de mejora continua.
- Necesitas **GPU** para entrenar en tiempo razonable (con `--device cpu` funciona
  pero es lento). Google Colab gratis sirve para empezar.
- Requiere **internet** (imágenes satelitales de Esri + datos de Overpass/OSM).
