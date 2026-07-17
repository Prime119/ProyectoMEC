"""
Sistema de Alertas Inteligentes — FALCON CFE.

Analiza el estado del sistema en tiempo real y genera alertas cuando detecta:
- Plantas en falla o fuera de línea
- Líneas sobrecargadas (>85%)
- Caída de frecuencia del sistema
- Temperatura crítica en plantas
- Múltiples plantas en mantenimiento simultáneo

Las alertas se acumulan en un historial exportable y se envían al frontend
para que MEC las comunique por voz.
"""
from __future__ import annotations

import json
import time
from datetime import datetime
from pathlib import Path
from dataclasses import dataclass, field

HISTORIAL_PATH = Path(__file__).resolve().parent.parent / "datos" / "historial_alertas.json"


@dataclass
class Alerta:
    timestamp: str
    severidad: str       # critica | alta | media | baja
    tipo: str            # falla_planta | sobrecarga_linea | frecuencia | temperatura | mantenimiento
    mensaje: str
    activo_id: str = ""
    activo_nombre: str = ""
    valor: float = 0.0
    umbral: float = 0.0


class MotorAlertas:
    """Analiza el estado del sistema y genera alertas inteligentes."""

    def __init__(self):
        self.alertas_activas: list[dict] = []
        self.historial: list[dict] = _cargar_historial()
        self._alertas_previas: set = set()  # para no repetir la misma alerta cada tick

    def analizar(self, plantas: list[dict], lineas: list[dict], resumen: dict) -> list[dict]:
        """Analiza el estado actual y genera alertas nuevas."""
        nuevas = []
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # 1. Plantas en falla
        for p in plantas:
            if p.get("estado") == "Falla":
                clave = f"falla_{p['id']}"
                if clave not in self._alertas_previas:
                    self._alertas_previas.add(clave)
                    nuevas.append({
                        "timestamp": ts, "severidad": "critica", "tipo": "falla_planta",
                        "mensaje": f"🚨 FALLA en {p['nombre']} — planta fuera de línea",
                        "activo_id": p.get("id", ""), "activo_nombre": p["nombre"],
                    })
            else:
                self._alertas_previas.discard(f"falla_{p.get('id','')}")

        # 2. Líneas sobrecargadas
        for l in lineas:
            if l.get("carga", 0) > 85:
                clave = f"sobrecarga_{l['id']}"
                if clave not in self._alertas_previas:
                    self._alertas_previas.add(clave)
                    nuevas.append({
                        "timestamp": ts, "severidad": "alta", "tipo": "sobrecarga_linea",
                        "mensaje": f"⚠️ Línea {l['nombre']} sobrecargada al {l['carga']:.0f}%",
                        "activo_id": l.get("id", ""), "activo_nombre": l["nombre"],
                        "valor": l["carga"], "umbral": 85,
                    })
            else:
                self._alertas_previas.discard(f"sobrecarga_{l.get('id','')}")

        # 3. Líneas en falla
        for l in lineas:
            if l.get("estado") == "Falla":
                clave = f"falla_linea_{l['id']}"
                if clave not in self._alertas_previas:
                    self._alertas_previas.add(clave)
                    nuevas.append({
                        "timestamp": ts, "severidad": "critica", "tipo": "falla_linea",
                        "mensaje": f"🚨 LÍNEA FUERA: {l['nombre']}",
                        "activo_id": l.get("id", ""), "activo_nombre": l["nombre"],
                    })
            else:
                self._alertas_previas.discard(f"falla_linea_{l.get('id','')}")

        # 4. Temperatura crítica en plantas
        for p in plantas:
            if p.get("temp", 0) > 560:
                clave = f"temp_{p['id']}"
                if clave not in self._alertas_previas:
                    self._alertas_previas.add(clave)
                    nuevas.append({
                        "timestamp": ts, "severidad": "alta", "tipo": "temperatura",
                        "mensaje": f"🔥 Temperatura crítica en {p['nombre']}: {p['temp']:.0f}°C",
                        "activo_id": p.get("id", ""), "activo_nombre": p["nombre"],
                        "valor": p["temp"], "umbral": 560,
                    })
            else:
                self._alertas_previas.discard(f"temp_{p.get('id','')}")

        # 5. Frecuencia baja del sistema
        freq = resumen.get("frecuencia_sistema", 60.0)
        if freq < 59.95:
            if "freq_baja" not in self._alertas_previas:
                self._alertas_previas.add("freq_baja")
                nuevas.append({
                    "timestamp": ts, "severidad": "critica", "tipo": "frecuencia",
                    "mensaje": f"⚡ Frecuencia del sistema baja: {freq:.3f} Hz (< 59.95 Hz)",
                    "valor": freq, "umbral": 59.95,
                })
        else:
            self._alertas_previas.discard("freq_baja")

        # 6. Muchas plantas en mantenimiento simultáneo
        en_manto = [p for p in plantas if p.get("estado") == "Mantenimiento"]
        if len(en_manto) >= 4:
            if "manto_multiple" not in self._alertas_previas:
                self._alertas_previas.add("manto_multiple")
                nombres = ", ".join(p["nombre"][:20] for p in en_manto[:4])
                nuevas.append({
                    "timestamp": ts, "severidad": "media", "tipo": "mantenimiento",
                    "mensaje": f"🔧 {len(en_manto)} plantas en mantenimiento simultáneo: {nombres}",
                })
        else:
            self._alertas_previas.discard("manto_multiple")

        # Guardar en historial
        if nuevas:
            self.historial.extend(nuevas)
            _guardar_historial(self.historial)

        self.alertas_activas = nuevas
        return nuevas

    def get_historial(self, limite: int = 100) -> list[dict]:
        """Devuelve las últimas N alertas del historial."""
        return self.historial[-limite:]


def _cargar_historial() -> list[dict]:
    if HISTORIAL_PATH.exists():
        try:
            return json.loads(HISTORIAL_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
    return []


def _guardar_historial(historial: list[dict]):
    # Limitar a 1000 eventos
    if len(historial) > 1000:
        historial = historial[-1000:]
    HISTORIAL_PATH.parent.mkdir(parents=True, exist_ok=True)
    HISTORIAL_PATH.write_text(json.dumps(historial, ensure_ascii=False), encoding="utf-8")
