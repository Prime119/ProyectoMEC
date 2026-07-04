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

    def __init__(self, modelo_path: str, umbral_confianza: float = 0.35,
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
            escala_x = img.width / self.tam_entrada
            escala_y = img.height / self.tam_entrada
            entrada = img.resize((self.tam_entrada, self.tam_entrada))
            arr = np.array(entrada, dtype=np.float32) / 255.0
            arr = np.transpose(arr, (2, 0, 1))[np.newaxis, ...]  # NCHW

            nombre_in = self._sesion.get_inputs()[0].name
            salidas = self._sesion.run(None, {nombre_in: arr})

            return self._parsear_salida(salidas[0], escala_x, escala_y, area)
        except Exception as e:
            print(f"[IA] Error en inferencia: {e}")
            return []

    def _parsear_salida(self, salida, escala_x, escala_y, area) -> list[Deteccion]:
        """Parsea la salida cruda de YOLO a detecciones georreferenciadas."""
        import numpy as np
        detecciones = []
        pred = np.squeeze(salida)
        if pred.ndim == 2 and pred.shape[0] < pred.shape[1]:
            pred = pred.T  # (num_boxes, 4+num_clases)

        for fila in pred:
            cx, cy, w, h = fila[:4]
            scores = fila[4:4 + NUM_CLASES]
            clase_idx = int(np.argmax(scores))
            conf = float(scores[clase_idx])
            if conf < self.umbral:
                continue
            clase_id = INDICE_A_CLASE.get(clase_idx)
            if not clase_id:
                continue
            # Escalar bbox a coords del mosaico
            x1 = (cx - w / 2) * escala_x
            y1 = (cy - h / 2) * escala_y
            x2 = (cx + w / 2) * escala_x
            y2 = (cy + h / 2) * escala_y
            px_c, py_c = (x1 + x2) / 2, (y1 + y2) / 2
            lon, lat = area.pixel_a_lonlat(px_c, py_c)
            tam_m = max(w * escala_x, h * escala_y) * area.metros_por_pixel()
            detecciones.append(Deteccion(
                clase_id=clase_id,
                nombre_clase=get_clase(clase_id).nombre,
                confianza=conf, lon=lon, lat=lat,
                bbox_px=(x1, y1, x2, y2),
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
