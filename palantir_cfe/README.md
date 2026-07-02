# 🛰️ Palantir CFE — Monitoreo de Infraestructura con Visión Satelital e IA

Sistema tipo Palantir para monitoreo en tiempo real de la infraestructura eléctrica
de CFE en el **Noroeste de México**: Baja California, Baja California Sur, Sonora,
Chihuahua y Sinaloa.

## Ejecutar

```bash
pip install -r ../requirements.txt
python -m palantir_cfe
```

## Módulos

| Módulo | Función |
|--------|---------|
| `dashboard.py` | Interfaz principal: mapa, KPIs, tablas, alertas, chat MEC, satélite |
| `datos_geograficos.py` | Base de datos real: 28 plantas, 19 subestaciones, 15 líneas |
| `simulador_telemetria.py` | Telemetría simulada en tiempo real de toda la infraestructura |
| `catalogo_activos.py` | Taxonomía de 21 clases de activos detectables |
| `satelite.py` | Descarga y georreferenciación de imágenes satelitales |
| `deteccion_ia.py` | Motor de detección de infraestructura (3 niveles) |
| `visor_satelital.py` | Visor con overlay de detecciones IA |
| `modelos_3d.py` | Geometría 3D holográfica de cada tipo de estructura |
| `vista_3d.py` | Gemelo digital 3D con gráficas de monitoreo en tiempo real |

## 🧊 Gemelo Digital 3D (pestaña 🧊 3D)

Cuando seleccionas una estructura de CFE, se renderiza en 3D con estética
holográfica (wireframe brillante estilo Palantir/Tron):

- **Piso holográfico** con rejilla, edificios de contexto urbano alrededor
- **Estructuras modeladas en 3D:** torres de enfriamiento hiperbólicas,
  chimeneas, aerogeneradores, torres de transmisión de celosía, postes,
  paneles solares, presas, subestaciones, edificios
- **Cámara con órbita automática** (efecto showroom)
- **Tarjeta de información** con datos del activo (capacidad, coords, tipo)
- **Gráficas de monitoreo en tiempo real** al lado: generación, temperatura, vibración

Requiere `PyOpenGL`. Si no está instalado, el resto del dashboard funciona igual.


## 🤖 Detección con IA — Cómo funciona

El sistema detecta y **geolocaliza con coordenadas exactas** 21 tipos de activos:

**Generación:** Hidroeléctrica, Eólica, Termoeléctrica, Solar, Nucleoeléctrica,
Ciclo Combinado, Carboeléctrica
**Transmisión:** Subestación, Torre Grande/Mediana/Chica, Línea de Transmisión, Transformador
**Administrativo:** Oficinas Centrales, Oficina Regional, Oficina
**Comercial:** Centro de Atención, Centro de Capacitación, Cajero Automático
**Logística/Medición:** Almacén, Medidor

### Los 3 niveles del motor de detección

El motor (`MotorDeteccion`) combina tres estrategias:

**1. Detector de activos conocidos** ✅ *Funciona hoy, precisión exacta*
Proyecta las coordenadas reales de la base de datos sobre la imagen satelital.
Sirve para ubicar y verificar plantas y subestaciones catalogadas.

**2. Detector ONNX/YOLO** 🔌 *Conectable — requiere tu modelo entrenado*
Ejecuta un modelo de visión (YOLOv8) sobre la imagen para detectar activos
nuevos no catalogados (torres, transformadores, medidores, etc).

**3. Detector simulado** 🎭 *Demo del pipeline*
Genera detecciones plausibles para demostrar el flujo completo sin modelo entrenado.
Se usa automáticamente cuando no hay modelo real conectado.

## 🎓 Cómo conectar un modelo de IA REAL

Para detección satelital real necesitas entrenar un modelo. Pasos:

### 1. Reunir datos de entrenamiento
- Descarga imágenes satelitales de ubicaciones conocidas de CFE
- Etiqueta los activos (bounding boxes) con las 21 clases de `catalogo_activos.py`
- Herramientas: [Roboflow](https://roboflow.com), [CVAT](https://cvat.ai), LabelImg

### 2. Entrenar un modelo YOLOv8
```python
from ultralytics import YOLO
model = YOLO("yolov8m.pt")          # modelo base
model.train(data="cfe_dataset.yaml", epochs=100, imgsz=640)
model.export(format="onnx")          # exportar a ONNX
```
El `cfe_dataset.yaml` debe tener las 21 clases en el mismo orden que
`CLASES_ORDENADAS` en `catalogo_activos.py`.

### 3. Conectar el modelo
```bash
# Opción A: variable de entorno
export PALANTIR_MODELO_ONNX=/ruta/a/tu/modelo.onnx
python -m palantir_cfe

# Opción B: en código
from palantir_cfe.deteccion_ia import MotorDeteccion
motor = MotorDeteccion(modelo_onnx="/ruta/a/modelo.onnx")
```

Instala también: `pip install onnxruntime` (o `onnxruntime-gpu` con CUDA).

## 🗺️ Imágenes satelitales

Usa **Esri World Imagery** (dominio público, sin API key). Las teselas se cachean
localmente en `palantir_cfe/cache_tiles/`.

La georreferenciación es exacta: cada pixel del mosaico se convierte a lon/lat real
mediante proyección Web Mercator (EPSG:3857). Por eso las detecciones tienen
coordenadas precisas.

## ⚠️ Nota sobre la detección real

La detección por IA de infraestructura en satélite es un problema real y resoluble,
pero **requiere un modelo entrenado con datos etiquetados de CFE**. El framework
completo está listo: solo conecta tu modelo `.onnx` y el sistema hará el resto
(inferencia + georreferenciación + overlay). Sin modelo, el sistema funciona en
modo simulado para demostrar el pipeline end-to-end.
