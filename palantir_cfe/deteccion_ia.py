"""
Motor de Detección con IA — Palantir CFE.

Detecta y geolocaliza infraestructura de CFE en imágenes satelitales.

Arquitectura de 3 niveles (de más a menos confiable):

  1. DETECTOR CONOCIDO (BaseConocida): Usa la base de datos georreferenciada de
     activos ya conocidos (plantas, subestaciones). Precisión = exacta. Sirve para
     "anclar" y verificar. Esto SÍ funciona hoy con datos reales.

  2. DETECTOR ONNX/YOLO (DetectorONNX): Ejecuta un modelo de visión entrenado
     (YOLOv8, etc.) sobre la imagen satelital. Detecta objetos nuevos no catalogados.
     Requiere un modelo .onnx entrenado con activos de CFE. Se conecta cuando lo tengas.

  3. DETECTOR SIMULADO (DetectorSimulado): Genera detecciones plausibles para
     demostrar el pipeline completo end-to-end sin necesidad de un modelo entrenado.

Todas las detecciones se devuelven georreferenciadas (lon/lat exacto) usando el
AreaSatelital, listas para pintarse en el mapa.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

from .catalogo_activos import (
    CATALOGO, ClaseActivo, get_clase, INDICE_A_CLASE, NUM_CLASES,
)
from .satelite import AreaSatelital



@dataclass
class Deteccion:
    """Una detección georreferenciada de un activo de CFE."""
    clase_id: str                 # ID de la clase detectada
    nombre_clase: str             # Nombre legible
    confianza: float              # 0-1, confianza del modelo
    lon: float                    # Longitud exacta del centro
    lat: float                    # Latitud exacta del centro
    # Bounding box en pixeles del mosaico (para dibujar sobre la imagen)
    bbox_px: tuple[float, float, float, float] = (0, 0, 0, 0)  # x1,y1,x2,y2
    tamaño_estimado_m: float = 0.0
    fuente: str = "ia"            # ia | conocido | simulado
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())

    @property
    def color(self) -> str:
        clase = get_clase(self.clase_id)
        return clase.color if clase else "#ffffff"

    @property
    def icono(self) -> str:
        clase = get_clase(self.clase_id)
        return clase.icono if clase else "●"


class DetectorBase:
    """Interfaz base para todos los detectores."""

    def detectar(self, area: AreaSatelital) -> list[Deteccion]:
        raise NotImplementedError


# =============================================================================
# NIVEL 1 — DETECTOR DE ACTIVOS CONOCIDOS (precisión exacta, funciona hoy)
# =============================================================================

class DetectorBaseConocida(DetectorBase):
    """
    'Detecta' activos ya catalogados en la base de datos georreferenciada.

    No usa visión: proyecta las coordenadas reales conocidas sobre la imagen.
    Es 100% preciso y sirve para anclar el análisis y validar el modelo de IA.
    """

    def detectar(self, area: AreaSatelital) -> list[Deteccion]:
        from .datos_geograficos import (
            PLANTAS_GENERACION, SUBESTACIONES, TipoPlanta
        )

        # Mapeo de tipo de planta -> clase del catálogo
        tipo_a_clase = {
            TipoPlanta.HIDROELECTRICA: "hidroelectrica",
            TipoPlanta.EOLICA: "eolica",
            TipoPlanta.TERMOELECTRICA: "termoelectrica",
            TipoPlanta.SOLAR: "solar",
            TipoPlanta.CICLO_COMBINADO: "ciclo_combinado",
            TipoPlanta.TURBOGAS: "termoelectrica",
            TipoPlanta.GEOTERMICA: "termoelectrica",
        }

        detecciones = []

        # Plantas de generación
        for p in PLANTAS_GENERACION:
            if not self._dentro(area, p.lon, p.lat):
                continue
            # Carboníferas por combustible
            clase_id = tipo_a_clase.get(p.tipo, "termoelectrica")
            if "Carbón" in p.combustible:
                clase_id = "carbonifera"
            px, py = area.lonlat_a_pixel(p.lon, p.lat)
            detecciones.append(Deteccion(
                clase_id=clase_id,
                nombre_clase=get_clase(clase_id).nombre if get_clase(clase_id) else clase_id,
                confianza=1.0,
                lon=p.lon, lat=p.lat,
                bbox_px=(px - 30, py - 30, px + 30, py + 30),
                tamaño_estimado_m=200,
                fuente="conocido",
            ))

        # Subestaciones
        for s in SUBESTACIONES:
            if not self._dentro(area, s.lon, s.lat):
                continue
            px, py = area.lonlat_a_pixel(s.lon, s.lat)
            detecciones.append(Deteccion(
                clase_id="subestacion",
                nombre_clase="Subestación",
                confianza=1.0,
                lon=s.lon, lat=s.lat,
                bbox_px=(px - 20, py - 20, px + 20, py + 20),
                tamaño_estimado_m=150,
                fuente="conocido",
            ))

        return detecciones

    @staticmethod
    def _dentro(area: AreaSatelital, lon: float, lat: float) -> bool:
        return (area.lon_min <= lon <= area.lon_max and
                area.lat_min <= lat <= area.lat_max)



# =============================================================================
# NIVEL 2 — DETECTOR ONNX / YOLO (modelo entrenado, conectable)
# =============================================================================

class DetectorONNX(DetectorBase):
    """
    Ejecuta un modelo de detección entrenado (YOLOv8 exportado a ONNX) sobre
    la imagen satelital.

    Para usarlo necesitas:
      1. Un modelo .onnx entrenado con las 21 clases de catalogo_activos.py
      2. onnxruntime instalado: pip install onnxruntime
      3. Pillow y numpy: pip install pillow numpy

    El modelo debe recibir imágenes 640x640 RGB y devolver detecciones en el
    formato estándar de YOLO: [x, y, w, h, conf, clase...].
    """

    def __init__(self, modelo_path: str, umbral_confianza: float = 0.20,
                 tam_entrada: int = 640):
        self.modelo_path = modelo_path
        self.umbral = umbral_confianza
        self.tam_entrada = tam_entrada
        self._sesion = None
        self._disponible = False
        self._cargar()

    def _cargar(self):
        if not Path(self.modelo_path).exists():
            print(f"[IA] Modelo no encontrado: {self.modelo_path}")
            return
        try:
            import onnxruntime as ort
            providers = ["CPUExecutionProvider"]
            if ort.get_device() == "GPU":
                providers.insert(0, "CUDAExecutionProvider")
            self._sesion = ort.InferenceSession(self.modelo_path, providers=providers)
            # Auto-detectar el tamaño de entrada del modelo (ej. 640 o 960)
            try:
                shape = self._sesion.get_inputs()[0].shape  # [1,3,H,W]
                h = shape[2]
                if isinstance(h, int) and h > 0:
                    self.tam_entrada = h
            except Exception:
                pass
            self._disponible = True
            print(f"[IA] Modelo ONNX cargado ({self.tam_entrada}px): {self.modelo_path}")
        except ImportError:
            print("[IA] onnxruntime no instalado. pip install onnxruntime")
        except Exception as e:
            print(f"[IA] Error cargando modelo: {e}")

    @property
    def disponible(self) -> bool:
        return self._disponible

    def detectar(self, area: AreaSatelital) -> list[Deteccion]:
        if not self._disponible or area.imagen is None:
            return []
        try:
            import numpy as np
            from PIL import Image

            img = area.imagen
            S = self.tam_entrada
            # LETTERBOX: redimensiona preservando proporción + relleno gris (igual
            # que el entrenamiento de YOLO). Evita deformar la imagen y corregir
            # así la posición de las detecciones.
            w0, h0 = img.width, img.height
            r = min(S / w0, S / h0)
            nw, nh = int(round(w0 * r)), int(round(h0 * r))
            dw, dh = (S - nw) // 2, (S - nh) // 2
            lienzo = Image.new("RGB", (S, S), (114, 114, 114))
            lienzo.paste(img.resize((nw, nh)), (dw, dh))

            arr = np.array(lienzo, dtype=np.float32) / 255.0
            arr = np.transpose(arr, (2, 0, 1))[np.newaxis, ...]  # NCHW

            nombre_in = self._sesion.get_inputs()[0].name
            salidas = self._sesion.run(None, {nombre_in: arr})

            return self._parsear_salida(salidas[0], r, dw, dh, area)
        except Exception as e:
            print(f"[IA] Error en inferencia: {e}")
            return []

    @staticmethod
    def _nms(cajas, iou_thr: float = 0.45):
        """Non-Maximum Suppression por clase: colapsa cajas duplicadas del mismo objeto."""
        import numpy as np
        x1, y1, x2, y2 = cajas[:, 0], cajas[:, 1], cajas[:, 2], cajas[:, 3]
        scores, clases = cajas[:, 4], cajas[:, 5]
        areas = (x2 - x1) * (y2 - y1)
        orden = scores.argsort()[::-1]
        keep = []
        while orden.size > 0:
            i = orden[0]
            keep.append(i)
            if orden.size == 1:
                break
            resto = orden[1:]
            xx1 = np.maximum(x1[i], x1[resto]); yy1 = np.maximum(y1[i], y1[resto])
            xx2 = np.minimum(x2[i], x2[resto]); yy2 = np.minimum(y2[i], y2[resto])
            w = np.maximum(0.0, xx2 - xx1); h = np.maximum(0.0, yy2 - yy1)
            inter = w * h
            iou = inter / (areas[i] + areas[resto] - inter + 1e-9)
            # Suprimir solo cajas MUY solapadas de la MISMA clase
            supr = (iou > iou_thr) & (clases[resto] == clases[i])
            orden = resto[~supr]
        return keep

    def _parsear_salida(self, salida, r, dw, dh, area) -> list[Deteccion]:
        """Parsea la salida cruda de YOLO -> deshace letterbox -> NMS -> georreferencia."""
        import numpy as np
        pred = np.squeeze(salida)
        if pred.ndim == 2 and pred.shape[0] < pred.shape[1]:
            pred = pred.T  # (num_boxes, 4+num_clases)

        cajas = []  # [x1, y1, x2, y2, conf, clase_idx] en pixeles del mosaico
        for fila in pred:
            cx, cy, w, h = fila[:4]
            scores = fila[4:4 + NUM_CLASES]
            clase_idx = int(np.argmax(scores))
            conf = float(scores[clase_idx])
            if conf < self.umbral:
                continue
            # Esquinas en el espacio de entrada del modelo (con letterbox)
            x1i, y1i = cx - w / 2, cy - h / 2
            x2i, y2i = cx + w / 2, cy + h / 2
            # Deshacer letterbox -> coords reales del mosaico
            x1 = (x1i - dw) / r; y1 = (y1i - dh) / r
            x2 = (x2i - dw) / r; y2 = (y2i - dh) / r
            cajas.append([x1, y1, x2, y2, conf, clase_idx])

        if not cajas:
            return []
        cajas = np.array(cajas, dtype=np.float32)
        keep = self._nms(cajas, iou_thr=0.85)

        detecciones = []
        mpp = area.metros_por_pixel()
        for i in keep:
            x1, y1, x2, y2, conf, clase_idx = cajas[i]
            clase_id = INDICE_A_CLASE.get(int(clase_idx))
            if not clase_id:
                continue
            px_c, py_c = (x1 + x2) / 2.0, (y1 + y2) / 2.0
            lon, lat = area.pixel_a_lonlat(float(px_c), float(py_c))
            tam_m = max(float(x2 - x1), float(y2 - y1)) * mpp
            detecciones.append(Deteccion(
                clase_id=clase_id,
                nombre_clase=get_clase(clase_id).nombre,
                confianza=float(conf), lon=lon, lat=lat,
                bbox_px=(float(x1), float(y1), float(x2), float(y2)),
                tamaño_estimado_m=tam_m, fuente="ia",
            ))
        return detecciones



# =============================================================================
# NIVEL 3 — DETECTOR SIMULADO (demo del pipeline sin modelo entrenado)
# =============================================================================

class DetectorSimulado(DetectorBase):
    """
    Genera detecciones plausibles alrededor de activos conocidos para demostrar
    el pipeline completo (detección -> georreferenciación -> overlay) sin necesitar
    un modelo entrenado.

    Simula lo que un modelo real detectaría: transformadores y torres alrededor de
    una subestación, torres a lo largo de una línea, medidores cerca de oficinas, etc.
    """

    def __init__(self, densidad: float = 1.0):
        self.densidad = densidad

    def detectar(self, area: AreaSatelital) -> list[Deteccion]:
        from .datos_geograficos import SUBESTACIONES, PLANTAS_GENERACION
        detecciones = []

        # Alrededor de cada subestación en el área: transformadores + torres
        for s in SUBESTACIONES:
            if not self._dentro(area, s.lon, s.lat):
                continue
            # Transformadores dentro del patio
            for _ in range(int(random.randint(2, 5) * self.densidad)):
                detecciones.append(self._detectar_cerca(
                    area, s.lon, s.lat, "transformador", radio_m=80,
                    conf_range=(0.72, 0.94)))
            # Torres de salida de líneas
            for _ in range(int(random.randint(3, 6) * self.densidad)):
                clase = random.choice(["torre_grande", "torre_mediana"])
                detecciones.append(self._detectar_cerca(
                    area, s.lon, s.lat, clase, radio_m=300,
                    conf_range=(0.60, 0.88)))

        # Alrededor de plantas: transformadores, torres, almacenes
        for p in PLANTAS_GENERACION:
            if not self._dentro(area, p.lon, p.lat):
                continue
            for _ in range(int(random.randint(1, 3) * self.densidad)):
                clase = random.choice(["transformador", "torre_grande", "almacen"])
                detecciones.append(self._detectar_cerca(
                    area, p.lon, p.lat, clase, radio_m=250,
                    conf_range=(0.65, 0.90)))

        return [d for d in detecciones if d is not None]

    def _detectar_cerca(self, area, lon, lat, clase_id, radio_m, conf_range):
        """Genera una detección simulada cerca de un punto."""
        import math
        clase = get_clase(clase_id)
        if not clase:
            return None
        # Desplazamiento aleatorio dentro del radio
        ang = random.uniform(0, 2 * math.pi)
        r = random.uniform(0, radio_m)
        dlat = (r * math.sin(ang)) / 111320.0
        dlon = (r * math.cos(ang)) / (111320.0 * math.cos(math.radians(lat)))
        nlon, nlat = lon + dlon, lat + dlat
        if not self._dentro(area, nlon, nlat):
            return None
        px, py = area.lonlat_a_pixel(nlon, nlat)
        tam_m = random.uniform(clase.tamaño_min_m, min(clase.tamaño_max_m, 50))
        tam_px = tam_m / max(area.metros_por_pixel(), 0.1)
        return Deteccion(
            clase_id=clase_id, nombre_clase=clase.nombre,
            confianza=round(random.uniform(*conf_range), 2),
            lon=nlon, lat=nlat,
            bbox_px=(px - tam_px/2, py - tam_px/2, px + tam_px/2, py + tam_px/2),
            tamaño_estimado_m=round(tam_m, 1), fuente="simulado",
        )

    @staticmethod
    def _dentro(area, lon, lat):
        return (area.lon_min <= lon <= area.lon_max and
                area.lat_min <= lat <= area.lat_max)


# =============================================================================
# MOTOR PRINCIPAL — Combina los detectores
# =============================================================================

class MotorDeteccion:
    """
    Motor principal que orquesta los detectores disponibles.

    Estrategia:
      - Siempre usa DetectorBaseConocida (activos reales, precisión exacta)
      - Si hay un modelo ONNX, lo usa para detectar activos nuevos
      - Si no hay modelo, usa el DetectorSimulado para demostrar el pipeline
    """

    def __init__(self, modelo_onnx: str | None = None, usar_simulado: bool = True):
        self.det_conocido = DetectorBaseConocida()
        self.det_onnx: Optional[DetectorONNX] = None
        self.det_simulado: Optional[DetectorSimulado] = None

        if modelo_onnx:
            self.det_onnx = DetectorONNX(modelo_onnx)
            if not self.det_onnx.disponible:
                self.det_onnx = None

        # Solo usar simulado si NO hay modelo real
        if usar_simulado and self.det_onnx is None:
            self.det_simulado = DetectorSimulado()

    @property
    def modo(self) -> str:
        if self.det_onnx:
            return "IA REAL (ONNX)"
        if self.det_simulado:
            return "SIMULADO (demo)"
        return "SOLO CONOCIDOS"

    def analizar(self, area: AreaSatelital) -> list[Deteccion]:
        """Analiza un área satelital y devuelve todas las detecciones."""
        detecciones = list(self.det_conocido.detectar(area))
        if self.det_onnx:
            detecciones.extend(self.det_onnx.detectar(area))
        elif self.det_simulado:
            detecciones.extend(self.det_simulado.detectar(area))
        return detecciones

    def resumen_detecciones(self, detecciones: list[Deteccion]) -> dict:
        """Cuenta detecciones por clase."""
        conteo = {}
        for d in detecciones:
            conteo[d.nombre_clase] = conteo.get(d.nombre_clase, 0) + 1
        return dict(sorted(conteo.items(), key=lambda x: -x[1]))
