"""
Datos reales de CENACE — Centro Nacional de Control de Energía.

Consulta los datos públicos de generación y demanda del Sistema Interconectado
Nacional (SIN) para la región Noroeste de México.

CENACE publica:
- Generación real por tipo de tecnología (eólica, solar, térmica, etc.)
- Demanda del sistema por región de control
- Frecuencia del sistema

Fuente: https://www.cenace.gob.mx/paginas/publicas/info/DemandaRegional.aspx
API no oficial (scraping de datos públicos).
"""
from __future__ import annotations

import json
import time
from datetime import datetime
from pathlib import Path

CACHE_DIR = Path(__file__).resolve().parent / "cache_cenace"
CACHE_DIR.mkdir(parents=True, exist_ok=True)


def obtener_datos_cenace() -> dict:
    """
    Intenta obtener datos reales de CENACE para la región Noroeste.
    Si falla (sin internet, API cambia, etc.), devuelve datos estimados
    basados en la hora del día (más realistas que los puramente aleatorios).

    Retorna: {
        "generacion_mw": float,
        "demanda_mw": float,
        "frecuencia_hz": float,
        "por_tipo": {"termica": X, "ciclo_combinado": X, "eolica": X, ...},
        "fuente": "cenace_real" | "estimado_hora",
        "timestamp": str,
    }
    """
    # Intentar datos reales primero
    datos = _consultar_cenace_real()
    if datos:
        return datos

    # Fallback: estimación basada en la hora del día (más realista que random)
    return _estimar_por_hora()


def _consultar_cenace_real() -> dict | None:
    """
    Intenta consultar la API/página pública de CENACE.
    CENACE no tiene una API REST pública estable, así que esto puede fallar.
    """
    try:
        import httpx
        # CENACE publica un resumen en esta URL (puede cambiar)
        url = "https://www.cenace.gob.mx/GraficaDemanda.aspx"
        r = httpx.get(url, timeout=10, headers={"User-Agent": "FALCON-CFE/1.0"})
        if r.status_code == 200 and "Noroeste" in r.text:
            # Intentar extraer el valor de demanda del Noroeste
            # (esto es frágil y puede romperse si CENACE cambia su página)
            import re
            match = re.search(r'Noroeste[^0-9]*([0-9,]+)\s*MW', r.text)
            if match:
                demanda = float(match.group(1).replace(",", ""))
                return {
                    "generacion_mw": demanda * 1.03,  # generación ≈ demanda + pérdidas
                    "demanda_mw": demanda,
                    "frecuencia_hz": 60.0,
                    "por_tipo": _estimar_mix_por_hora(),
                    "fuente": "cenace_real",
                    "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                }
    except Exception:
        pass
    return None


def _estimar_por_hora() -> dict:
    """
    Estimación realista basada en la hora del día y la capacidad instalada
    real de la región Noroeste (~9,800 MW instalados).

    Los patrones de demanda en el Noroeste de México son:
    - Mínimo: 2-6 AM (~3,500 MW)
    - Medio: 7-13 y 21-1 AM (~5,000 MW)
    - Pico: 14-20 PM (~6,500 MW en verano, ~5,500 en invierno)
    """
    import math
    hora = datetime.now().hour
    mes = datetime.now().month

    # Factor estacional (verano = más demanda por AC)
    es_verano = mes in (5, 6, 7, 8, 9, 10)
    base = 5500 if es_verano else 4800

    # Curva de demanda diaria (sinusoidal con pico a las 17h)
    pico_offset = math.sin(math.pi * (hora - 5) / 12) if 5 <= hora <= 21 else -0.3
    demanda = base + pico_offset * (1800 if es_verano else 1200)
    demanda = max(3200, demanda)

    # Mix de generación por tipo (basado en capacidad instalada real)
    mix = _estimar_mix_por_hora()
    generacion = sum(mix.values())

    return {
        "generacion_mw": round(generacion, 0),
        "demanda_mw": round(demanda, 0),
        "frecuencia_hz": round(60.0 + (generacion - demanda) / 50000, 3),
        "por_tipo": mix,
        "fuente": "estimado_hora",
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }


def _estimar_mix_por_hora() -> dict:
    """Estima la generación por tipo de tecnología según la hora."""
    import math
    hora = datetime.now().hour

    # Solar: depende de la hora (0 de noche, pico a las 13h)
    if 6 <= hora <= 19:
        solar = 350 * math.sin(math.pi * (hora - 6) / 13)
    else:
        solar = 0

    # Eólica: más estable, con algo de variación
    eolica = 180 + 60 * math.sin(hora * 0.5)

    # Geotérmica: constante (base load)
    geotermica = 520

    # Hidroeléctrica: relativamente constante
    hidro = 250

    # El resto es térmico (ciclo combinado + termoeléctrica + turbogás)
    # que se ajusta para cubrir la demanda
    demanda_estimada = 5200
    termico_total = max(2000, demanda_estimada - solar - eolica - geotermica - hidro)

    return {
        "ciclo_combinado": round(termico_total * 0.65),
        "termoelectrica": round(termico_total * 0.20),
        "turbogas": round(termico_total * 0.10),
        "carbonifera": round(termico_total * 0.05),
        "solar": round(solar),
        "eolica": round(eolica),
        "geotermica": round(geotermica),
        "hidroelectrica": round(hidro),
    }
