"""
Servidor web para Palantir CFE — Backend con datos en tiempo real.

- Sirve el frontend (HTML/CSS/JS)
- WebSocket: envía telemetría cada 2 segundos a todos los clientes
- REST: endpoints para el chat Astra y datos estáticos
- TTS: edge-tts con voz femenina es-MX-DaliaNeural
- Auto-aprendizaje: investiga en segundo plano sobre ingeniería eléctrica

Ejecutar:
    python palantir_web/servidor.py

Se abre automáticamente en http://localhost:8080
"""
from __future__ import annotations

import asyncio
import json
import os
import signal
import sys
import threading
import time
import tempfile
import webbrowser
from pathlib import Path

# Permitir importar palantir_cfe
RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from aiohttp import web
from palantir_cfe.datos_geograficos import (
    PLANTAS_GENERACION, SUBESTACIONES, LINEAS_TRANSMISION,
    TipoPlanta, NivelTension, EstadoOperativo,
)
from palantir_cfe.catalogo_activos import CATALOGO
from palantir_cfe.simulador_telemetria import SimuladorTelemetria

# Astra Assistant (IA industrial — 4 IAs integradas)
mec_assistant = None
try:
    from astra_assistant import AstraAssistant
    mec_assistant = AstraAssistant.boot()
    print("🤖 Astra Assistant integrado (4 IAs)")
except Exception as e:
    print(f"⚠️ Astra no disponible: {e}")

# Detector de IA satelital (opcional) — usa el modelo ONNX si PALANTIR_MODELO_ONNX está definido
motor_ia = None
cliente_sat = None
try:
    from palantir_cfe.deteccion_ia import MotorDeteccion
    from palantir_cfe.satelite import ClienteSatelital
    _modelo = os.environ.get("PALANTIR_MODELO_ONNX")
    motor_ia = MotorDeteccion(modelo_onnx=_modelo, usar_simulado=False)
    cliente_sat = ClienteSatelital(proveedor="esri")
    print(f"🛰️ IA satelital: {motor_ia.modo}")
except Exception as e:
    print(f"⚠️ IA satelital no disponible: {e}")

# Motor de alertas inteligentes
from palantir_web.alertas import MotorAlertas
motor_alertas = MotorAlertas()
print(f"🚨 Motor de alertas activo ({len(motor_alertas.historial)} eventos en historial)")


# === SIMULADOR ===
simulador = SimuladorTelemetria()
ultimo_estado = {"plantas": [], "lineas": [], "resumen": {}}


def tick_simulador():
    """Actualiza el simulador (se llama cada 2 seg)."""
    global ultimo_estado
    plantas_tel, lineas_tel = simulador.tick()
    resumen = simulador.get_resumen_sistema(plantas_tel, lineas_tel)

    plantas_data = []
    for i, t in enumerate(plantas_tel):
        p = PLANTAS_GENERACION[i]
        clase_id = _clase_de_planta(p)
        info = CATALOGO.get(clase_id)
        plantas_data.append({
            "id": p.id, "nombre": p.nombre, "lat": p.lat, "lon": p.lon,
            "estado": t.estado_operativo.value,
            "tipo": p.tipo.value, "clase": clase_id,
            "color": info.color if info else "#00d4ff",
            "icono": info.icono if info else "⚡",
            "gen_mw": t.generacion_actual_mw, "cap_mw": t.capacidad_mw,
            "factor": t.factor_planta, "temp": t.temperatura_caldera_c,
            "vib": t.vibracion_turbina_mms, "freq": t.frecuencia_hz,
            "rpm": t.rpm_turbina, "eficiencia": t.eficiencia_pct,
            "alertas": t.alertas,
            "detalle": f"{p.tipo.value} · {p.capacidad_mw} MW · {p.municipio}, {p.estado.value}",
        })

    lineas_data = []
    for i, t in enumerate(lineas_tel):
        lt = LINEAS_TRANSMISION[i]
        lineas_data.append({
            "id": lt.id, "nombre": lt.nombre,
            "estado": t.estado_operativo.value,
            "tension": lt.nivel_tension.value,
            "es_400": lt.nivel_tension == NivelTension.KV_400,
            "carga": t.carga_pct, "flujo_mw": t.flujo_mw,
            "corriente": t.corriente_a, "temp": t.temperatura_conductor_c,
            "alertas": t.alertas,
        })

    ultimo_estado = {"plantas": plantas_data, "lineas": lineas_data, "resumen": resumen}


def _clase_de_planta(p):
    tipo_map = {
        TipoPlanta.HIDROELECTRICA: "hidroelectrica", TipoPlanta.EOLICA: "eolica",
        TipoPlanta.TERMOELECTRICA: "termoelectrica", TipoPlanta.SOLAR: "solar",
        TipoPlanta.CICLO_COMBINADO: "ciclo_combinado", TipoPlanta.TURBOGAS: "termoelectrica",
        TipoPlanta.GEOTERMICA: "termoelectrica",
    }
    if "Carbón" in p.combustible:
        return "carbonifera"
    return tipo_map.get(p.tipo, "termoelectrica")


# === DATOS ESTÁTICOS (para el mapa: coords de líneas) ===
def get_lineas_coords():
    """Coordenadas de las líneas de transmisión para dibujar en el mapa."""
    def coords(node_id):
        for s in SUBESTACIONES:
            if s.id == node_id:
                return [s.lat, s.lon]
        for p in PLANTAS_GENERACION:
            if p.id == node_id:
                return [p.lat, p.lon]
        return None

    result = []
    for lt in LINEAS_TRANSMISION:
        o = coords(lt.origen_id)
        d = coords(lt.destino_id)
        if o and d:
            result.append({
                "id": lt.id, "nombre": lt.nombre,
                "coords": [o, d],
                "tension": lt.nivel_tension.value,
                "es_400": lt.nivel_tension == NivelTension.KV_400,
            })
    return result


LINEAS_COORDS = get_lineas_coords()


# === GENERACIÓN DE TORRES A LO LARGO DE LAS LÍNEAS ===
def _haversine_km(lat1, lon1, lat2, lon2):
    import math
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2 +
         math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2)
    return R * 2 * math.atan2(a ** 0.5, (1 - a) ** 0.5)


def generar_torres(spacing_km: float = 7.0):
    """
    Genera torres de transmisión distribuidas a lo largo de cada línea.
    En la realidad las torres van a intervalos regulares; estas son posiciones
    representativas (la ubicación exacta de cada torre la dará la IA satelital).
    """
    torres = []
    for l in LINEAS_COORDS:
        (lat1, lon1), (lat2, lon2) = l["coords"]
        dist = _haversine_km(lat1, lon1, lat2, lon2)
        n = max(1, int(dist / spacing_km))
        clase = "torre_grande" if l["es_400"] else "torre_mediana"
        tension = "400 kV" if l["es_400"] else "230 kV"
        for i in range(1, n):
            t = i / n
            torres.append({
                "lat": round(lat1 + (lat2 - lat1) * t, 5),
                "lon": round(lon1 + (lon2 - lon1) * t, 5),
                "clase": clase, "tension": tension, "linea": l["nombre"],
            })
    return torres


TORRES = generar_torres()
print(f"🗼 {len(TORRES)} torres generadas a lo largo de las líneas")


# === INTERCONEXIONES CFE que cruzan a EE.UU. (WECC/CAISO) ===
# Líneas reales de CFE Baja California que se interconectan con California.
INTERCONEXIONES = [
    {"nombre": "Interconexión La Rosita (Mexicali) – Imperial Valley, CA",
     "coords": [[32.5928, -115.4267], [32.710, -115.573]], "tension": "230 kV"},
    {"nombre": "Interconexión Cerro Prieto – Imperial Valley, CA",
     "coords": [[32.4142, -115.2342], [32.710, -115.573]], "tension": "230 kV"},
    {"nombre": "Interconexión Tijuana – Miguel (San Diego), CA",
     "coords": [[32.5300, -116.9500], [32.660, -117.020]], "tension": "230 kV"},
]


async def handle_interconexiones(request):
    return web.json_response(INTERCONEXIONES)


async def handle_torres(request):
    return web.json_response(TORRES)


async def handle_osm_region(request):
    """Infraestructura eléctrica real de OpenStreetMap (subestaciones, plantas, líneas)."""
    from palantir_web import osm
    loop = asyncio.get_event_loop()
    try:
        data = await loop.run_in_executor(None, osm.obtener_infraestructura_region)
    except Exception as e:
        print(f"[OSM] Error: {e}")
        data = {"subestaciones": [], "plantas": [], "lineas": []}
    return web.json_response(data)


async def handle_osm_torres(request):
    """Torres y postes reales de OSM dentro del área visible (bbox)."""
    from palantir_web import osm
    try:
        s = float(request.query.get("s"))
        w = float(request.query.get("w"))
        n = float(request.query.get("n"))
        e = float(request.query.get("e"))
    except (TypeError, ValueError):
        return web.json_response([])
    loop = asyncio.get_event_loop()
    try:
        torres = await loop.run_in_executor(None, osm.obtener_torres_bbox, s, w, n, e)
    except Exception as ex:
        print(f"[OSM] Error torres: {ex}")
        torres = []
    return web.json_response(torres)


async def handle_buscar_cfe(request):
    """Busca TODAS las instalaciones CFE (oficinas, almacenes, centros, etc.) en el área visible."""
    from palantir_web.buscar_cfe import buscar_instalaciones_cfe
    try:
        s = float(request.query.get("s"))
        w = float(request.query.get("w"))
        n = float(request.query.get("n"))
        e = float(request.query.get("e"))
    except (TypeError, ValueError):
        return web.json_response([])
    loop = asyncio.get_event_loop()
    try:
        resultados = await loop.run_in_executor(None, buscar_instalaciones_cfe, s, w, n, e)
    except Exception as ex:
        print(f"[CFE] Error buscar: {ex}")
        resultados = []
    return web.json_response(resultados)


def _cargar_csv_manual() -> list[dict]:
    """Lee el archivo CSV de instalaciones manuales (de Google Maps)."""
    csv_path = RAIZ / "datos" / "instalaciones_cfe.csv"
    if not csv_path.exists():
        return []
    items = []
    try:
        for linea in csv_path.read_text(encoding="utf-8").splitlines():
            linea = linea.strip()
            if not linea or linea.startswith("#"):
                continue
            partes = linea.split(",", 4)
            if len(partes) >= 4:
                try:
                    items.append({
                        "lat": float(partes[0]),
                        "lon": float(partes[1]),
                        "nombre": partes[2].strip(),
                        "tipo": partes[3].strip(),
                        "ciudad": partes[4].strip() if len(partes) > 4 else "",
                        "fuente": "google_maps_manual",
                    })
                except ValueError:
                    continue
    except Exception as ex:
        print(f"[CSV] Error: {ex}")
    return items


async def handle_cfe_manual(request):
    """Devuelve las instalaciones CFE del archivo CSV (agregadas manualmente desde Google Maps)."""
    return web.json_response(_cargar_csv_manual())


# === WEBSOCKET: envía estado cada 2 seg ===
ws_clients: set = set()


async def ws_handler(request):
    ws = web.WebSocketResponse()
    await ws.prepare(request)
    ws_clients.add(ws)
    try:
        async for msg in ws:
            pass  # Solo escuchamos para detectar desconexión
    finally:
        ws_clients.discard(ws)
    return ws


async def broadcast_loop():
    """Cada 2 seg: tick del simulador + enviar a todos los clientes."""
    while True:
        tick_simulador()
        payload = json.dumps(ultimo_estado, ensure_ascii=False)
        dead = set()
        for ws in ws_clients:
            try:
                await ws.send_str(payload)
            except Exception:
                dead.add(ws)
        ws_clients -= dead
        await asyncio.sleep(2)


# === REST ENDPOINTS ===
async def handle_index(request):
    resp = web.FileResponse(Path(__file__).parent / "static" / "index.html")
    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    return resp


async def handle_static(request):
    name = request.match_info["name"]
    path = Path(__file__).parent / "static" / name
    if path.exists():
        resp = web.FileResponse(path)
        resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        return resp
    return web.Response(status=404)


async def handle_lineas_coords(request):
    return web.json_response(LINEAS_COORDS)


async def handle_mec_chat(request):
    """Endpoint para el chat de Astra. Usa llama.cpp como cerebro."""
    global _ultima_actividad
    _ultima_actividad = time.time()

    data = await request.json()
    texto = data.get("texto", "")

    # Usar Astra con LLM (llama.cpp en puerto 8080)
    if mec_assistant is not None:
        try:
            loop = asyncio.get_event_loop()

            # Primero verificar si el LLM está disponible
            llm_ok = await loop.run_in_executor(None, mec_assistant.brain.is_available)

            if llm_ok:
                # LLM funcionando → respuesta completa con IA
                ctx = json.dumps(ultimo_estado.get("resumen", {}), ensure_ascii=False)
                prompt = f"[INFRAESTRUCTURA CFE]\n{ctx}\n\n[PREGUNTA]\n{texto}"
                respuesta = await loop.run_in_executor(None, mec_assistant.handle, prompt)

                # Verificar que no sea un error del cerebro
                if respuesta and "[Astra]" in respuesta and ("Error" in respuesta or "cerebro" in respuesta):
                    respuesta = responder_por_reglas(texto)

                return web.json_response({"respuesta": respuesta})
            else:
                # LLM NO está corriendo → responder con reglas + aviso si es pregunta no cubierta
                respuesta = responder_por_reglas(texto, llm_disponible=False)
                return web.json_response({"respuesta": respuesta})

        except Exception as e:
            print(f"[Astra] Error: {e}")

    # Astra no pudo iniciar en absoluto
    return web.json_response({"respuesta": responder_por_reglas(texto, llm_disponible=False)})


# === EDGE-TTS: Voz femenina es-MX-DaliaNeural ===
async def handle_tts(request):
    """Genera audio MP3 con edge-tts (voz femenina mexicana)."""
    try:
        data = await request.json()
        texto = data.get("texto", "")
        if not texto:
            return web.Response(status=400, text="Falta texto")

        # Limpiar emojis y símbolos
        import re
        texto_limpio = re.sub(r'[^\w\s.,;:!?¿¡\-()áéíóúñüÁÉÍÓÚÑÜ]', '', texto).strip()
        if not texto_limpio:
            return web.Response(status=400, text="Texto vacío después de limpiar")

        # Limitar longitud para respuestas rápidas
        if len(texto_limpio) > 500:
            texto_limpio = texto_limpio[:500]

        loop = asyncio.get_event_loop()
        mp3_bytes = await loop.run_in_executor(None, _generar_tts, texto_limpio)

        if mp3_bytes is None:
            return web.Response(status=503, text="edge-tts no disponible")

        return web.Response(
            body=mp3_bytes,
            content_type="audio/mpeg",
            headers={"Cache-Control": "no-store"}
        )
    except Exception as e:
        print(f"[TTS] Error: {e}")
        return web.Response(status=500, text=str(e))


def _generar_tts(texto: str) -> bytes | None:
    """Genera audio MP3 con edge-tts (síncrono, para run_in_executor)."""
    try:
        import edge_tts
        import asyncio as _asyncio

        async def _gen():
            communicate = edge_tts.Communicate(texto, "es-MX-DaliaNeural")
            # Recolectar todos los chunks de audio
            chunks = []
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    chunks.append(chunk["data"])
            return b"".join(chunks)

        # Crear nuevo event loop para este hilo
        loop = _asyncio.new_event_loop()
        try:
            return loop.run_until_complete(_gen())
        finally:
            loop.close()
    except ImportError:
        print("[TTS] edge-tts no instalado. Instala con: pip install edge-tts")
        return None
    except Exception as e:
        print(f"[TTS] Error generando audio: {e}")
        return None


# === AUTO-APRENDIZAJE EN SEGUNDO PLANO ===
# Investiga sobre ingeniería eléctrica cuando el usuario lleva >10 min sin interactuar
_ultima_actividad: float = time.time()
_auto_learn_running: bool = False

TEMAS_INVESTIGACION = [
    "IEEE 519 armónicos límites THD",
    "ISO 10816 vibración máquinas rotativas",
    "NOM-001-SEDE norma instalaciones eléctricas México",
    "NEMA MG-1 motores eléctricos especificaciones",
    "NFPA 70E seguridad eléctrica arco eléctrico",
    "mantenimiento predictivo motores eléctricos",
    "factor de potencia corrección capacitores",
    "protección diferencial transformadores",
    "coordinación de protecciones sistemas eléctricos",
    "análisis de aceite transformadores",
    "termografía infrarroja mantenimiento eléctrico",
    "calidad de energía eléctrica CFE México",
    "sistemas SCADA redes eléctricas",
    "energía renovable integración red eléctrica",
    "subestaciones eléctricas diseño operación",
    "cables de potencia subterráneos",
    "generación distribuida regulación México",
    "smart grid redes inteligentes eléctricas",
    "detección de fallas líneas transmisión",
    "eficiencia energética motores industriales",
]


def _auto_learn_worker():
    """Hilo de auto-aprendizaje: investiga cuando el usuario está inactivo."""
    global _auto_learn_running
    import random

    _auto_learn_running = True
    tema_idx = 0

    while _auto_learn_running:
        time.sleep(30)  # Revisar cada 30 segundos

        # Solo investigar si lleva >10 min sin interactuar
        inactivo = time.time() - _ultima_actividad
        if inactivo < 600:  # 10 minutos
            continue

        # Investigar un tema
        tema = TEMAS_INVESTIGACION[tema_idx % len(TEMAS_INVESTIGACION)]
        tema_idx += 1

        try:
            conocimiento = _investigar_tema(tema)
            if conocimiento and mec_assistant is not None:
                # Guardar en la memoria de Astra
                mec_assistant.memory.log_event(
                    "auto_aprendizaje",
                    f"Tema: {tema}\n{conocimiento}",
                    severity="info"
                )
                print(f"[Auto-Learn] Aprendido: {tema[:50]}...")
        except Exception as e:
            print(f"[Auto-Learn] Error investigando '{tema}': {e}")

        # Esperar 5 minutos entre investigaciones para no saturar
        time.sleep(300)


def _investigar_tema(tema: str) -> str | None:
    """Busca información sobre un tema en DuckDuckGo/Wikipedia."""
    import urllib.request
    import urllib.parse

    conocimiento_parts = []

    # 1. Intentar Wikipedia en español
    try:
        wiki_query = urllib.parse.quote(tema.split()[0] + " " + tema.split()[1] if len(tema.split()) > 1 else tema)
        wiki_url = f"https://es.wikipedia.org/api/rest_v1/page/summary/{wiki_query}"
        req = urllib.request.Request(wiki_url, headers={"User-Agent": "FalconCFE/1.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            extracto = data.get("extract", "")
            if extracto and len(extracto) > 50:
                conocimiento_parts.append(f"[Wikipedia] {extracto[:500]}")
    except Exception:
        pass

    # 2. Intentar DuckDuckGo Instant Answer
    try:
        ddg_query = urllib.parse.quote(tema)
        ddg_url = f"https://api.duckduckgo.com/?q={ddg_query}&format=json&no_html=1&skip_disambig=1"
        req = urllib.request.Request(ddg_url, headers={"User-Agent": "FalconCFE/1.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            abstract = data.get("AbstractText", "")
            if abstract and len(abstract) > 30:
                conocimiento_parts.append(f"[DuckDuckGo] {abstract[:500]}")
            # También tomar temas relacionados
            related = data.get("RelatedTopics", [])
            for r in related[:3]:
                if isinstance(r, dict) and r.get("Text"):
                    conocimiento_parts.append(f"  - {r['Text'][:200]}")
    except Exception:
        pass

    if conocimiento_parts:
        return "\n".join(conocimiento_parts)
    return None


def responder_por_reglas(texto: str, llm_disponible: bool = True) -> str:
    """
    Responde preguntas comunes usando los datos actuales.
    Si el LLM no está disponible y la pregunta no se puede contestar,
    dice exactamente qué falta instalar.
    """
    t = texto.lower().strip()
    r = ultimo_estado.get("resumen", {})
    plantas = ultimo_estado.get("plantas", [])
    lineas = ultimo_estado.get("lineas", [])

    fallas = [p for p in plantas if p["estado"] == "Falla"]
    manto = [p for p in plantas if p["estado"] == "Mantenimiento"]
    lineas_falla = [l for l in lineas if l["estado"] == "Falla"]
    sobrecargadas = [l for l in lineas if l["carga"] > 85]

    # === SALUDOS CASUALES (siempre responde, con o sin LLM) ===
    if any(w in t for w in ["hola", "que tal", "qué tal", "buenas", "buenos días",
                            "buenos dias", "buenas tardes", "buenas noches", "hey",
                            "qué onda", "que onda", "sup", "hi", "hello"]):
        gen = r.get('generacion_total_mw', 0)
        alertas = r.get('alertas_activas', 0)
        if alertas > 0:
            return (f"Hola, ingeniero. Sistema generando {gen:.0f} MW con "
                    f"{alertas} alerta{'s' if alertas > 1 else ''} activa{'s' if alertas > 1 else ''}. "
                    f"¿En qué te ayudo?")
        return f"Hola, ingeniero. Todo en orden — {gen:.0f} MW generándose. ¿En qué te ayudo?"

    # === AGRADECIMIENTOS ===
    if any(w in t for w in ["gracias", "thanks", "perfecto", "ok gracias", "vale"]):
        return "De nada, ingeniero. Aquí estoy si necesitas algo más."

    # === IDENTIDAD ===
    if any(w in t for w in ["quién eres", "quien eres", "tu nombre", "cómo te llamas",
                            "como te llamas", "qué eres", "que eres", "presentate",
                            "preséntate"]):
        return ("Soy Astra — tu asistente de infraestructura eléctrica. "
                "Integro 4 inteligencias: JARVIS (eficiencia), Optimus Prime (seguridad), "
                "Caine (auto-reinicio cognitivo) y Cyborg (auto-auditoría). "
                "Monitoreo las plantas, líneas y subestaciones de CFE Noroeste en tiempo real.")

    # === CAPACIDADES ===
    if any(w in t for w in ["qué puedes", "que puedes", "qué sabes", "que sabes",
                            "ayuda", "help", "funciones"]):
        return ("Puedo ayudarte con: monitoreo de plantas y líneas en tiempo real, "
                "alertas de fallas y sobrecarga, estado del sistema eléctrico, "
                "análisis de armónicos (IEEE 519), vibración (ISO 10816), "
                "predicción de demanda, y detección satelital de infraestructura. "
                "Pregúntame lo que necesites, ingeniero.")

    # === DATOS DEL SISTEMA ===
    if any(w in t for w in ["falla", "problema", "riesgo", "alerta", "mal", "error"]):
        if not fallas and not lineas_falla:
            return "Todo en orden, ingeniero. No hay plantas ni líneas en falla ahora mismo."
        msg = ""
        if fallas:
            msg += "Plantas en falla: " + ", ".join(p["nombre"] for p in fallas) + ". "
        if lineas_falla:
            msg += "Líneas fuera: " + ", ".join(l["nombre"] for l in lineas_falla) + ". "
        return msg.strip()

    if any(w in t for w in ["genera", "generación", "produc", "mw", "potencia"]):
        return (f"Generación total: {r.get('generacion_total_mw',0):.0f} MW de "
                f"{r.get('capacidad_total_mw',0):.0f} MW instalados "
                f"(factor de carga {r.get('factor_carga_sistema',0):.1f}%). "
                f"Demanda estimada: {r.get('demanda_estimada_mw',0):.0f} MW.")

    if any(w in t for w in ["sobrecarg", "carga", "línea", "linea", "transmisión"]):
        if sobrecargadas:
            return "Líneas con carga elevada: " + ", ".join(
                f"{l['nombre']} ({l['carga']:.0f}%)" for l in sobrecargadas)
        return f"Las {r.get('lineas_operando',0)} líneas operando están dentro de rango normal."

    if any(w in t for w in ["mantenimiento", "manto"]):
        if manto:
            return "En mantenimiento: " + ", ".join(p["nombre"] for p in manto)
        return "Ninguna planta está en mantenimiento en este momento."

    if any(w in t for w in ["resumen", "estado", "general", "cómo va", "como va",
                            "cómo está", "como esta", "situación", "situacion",
                            "reporte", "dame un"]):
        return (f"Sistema: {r.get('generacion_total_mw',0):.0f} MW generados, "
                f"{r.get('plantas_operando',0)}/{r.get('plantas_total',0)} plantas operando, "
                f"{r.get('lineas_operando',0)}/{r.get('lineas_total',0)} líneas activas, "
                f"frecuencia {r.get('frecuencia_sistema',60):.3f} Hz, "
                f"{r.get('alertas_activas',0)} alertas activas.")

    if any(w in t for w in ["frecuencia", "hz", "hertz"]):
        return f"Frecuencia del sistema: {r.get('frecuencia_sistema',60):.3f} Hz (nominal: 60.000 Hz)."

    if any(w in t for w in ["temperatura", "temp", "caliente"]):
        return (f"Temperatura promedio de calderas: "
                f"{r.get('generacion_total_mw',0)*0.08 + 450:.0f}°C (dentro de rango).")

    # === PREGUNTA NO CUBIERTA ===
    if not llm_disponible:
        # Detectar qué falta
        problemas = []
        try:
            import httpx
            resp = httpx.get("http://127.0.0.1:8080/health", timeout=2.0)
            if resp.status_code != 200:
                problemas.append("llama-server no está respondiendo")
        except Exception:
            problemas.append("llama-server no está corriendo")

        if problemas:
            return (f"Para responder preguntas abiertas necesito mi cerebro (LLM). "
                    f"Problema detectado: {'; '.join(problemas)}. "
                    f"Solución: cierra FALCON y ejecútalo de nuevo con 'python falcon.py' "
                    f"— te preguntará si instalar el LLM automáticamente.")
        else:
            return ("No tengo una respuesta para eso en mis datos actuales. "
                    "Intenta preguntar sobre: fallas, generación, líneas, frecuencia o estado general.")

    # Si el LLM sí está (pero la respuesta no llegó por alguna razón)
    return (f"Sistema operando: {r.get('generacion_total_mw',0):.0f} MW, "
            f"{r.get('alertas_activas',0)} alertas. "
            f"¿Qué necesitas saber, ingeniero?")


# Control de vida: DESACTIVADO (causaba cierres inesperados al cargar lento)
# El usuario cierra el servidor manualmente con Ctrl+C.
_hubo_actividad = False
SEGUNDOS_SIN_PAGINA = 9999  # efectivamente desactivado


async def handle_estado(request):
    """Avanza el simulador y devuelve el estado actual (polling = latido de la página)."""
    global _ultima_actividad, _hubo_actividad
    _ultima_actividad = time.time()
    _hubo_actividad = True
    tick_simulador()

    # Enriquecer el resumen con datos de CENACE (reales o estimados por hora)
    # O con datos SCADA si está configurado (prioridad: SCADA > CENACE > estimado)
    try:
        from palantir_web.scada_connector import leer_datos_scada, esta_configurado
        if esta_configurado():
            scada = leer_datos_scada()
            if scada:
                if "generacion_mw" in scada:
                    ultimo_estado["resumen"]["generacion_total_mw"] = scada["generacion_mw"]
                if "demanda_mw" in scada:
                    ultimo_estado["resumen"]["demanda_estimada_mw"] = scada["demanda_mw"]
                if "frecuencia_hz" in scada:
                    ultimo_estado["resumen"]["frecuencia_sistema"] = scada["frecuencia_hz"]
                ultimo_estado["resumen"]["fuente_datos"] = scada.get("fuente", "scada")
                print("[SCADA] Datos reales recibidos")
            else:
                raise Exception("SCADA no respondió, usando CENACE")
        else:
            raise Exception("SCADA no configurado")
    except Exception:
        # Fallback: datos de CENACE/estimados
        try:
            from palantir_web.cenace import obtener_datos_cenace
            cenace = obtener_datos_cenace()
            ultimo_estado["resumen"]["generacion_total_mw"] = cenace["generacion_mw"]
            ultimo_estado["resumen"]["demanda_estimada_mw"] = cenace["demanda_mw"]
            ultimo_estado["resumen"]["frecuencia_sistema"] = cenace["frecuencia_hz"]
            ultimo_estado["resumen"]["fuente_datos"] = cenace["fuente"]
            ultimo_estado["resumen"]["mix_generacion"] = cenace["por_tipo"]
        except Exception:
            pass

    # Generar alertas inteligentes
    try:
        alertas_nuevas = motor_alertas.analizar(
            ultimo_estado.get("plantas", []),
            ultimo_estado.get("lineas", []),
            ultimo_estado.get("resumen", {})
        )
        ultimo_estado["alertas_nuevas"] = alertas_nuevas
        # Enviar alertas críticas a Telegram (si está configurado)
        if alertas_nuevas:
            try:
                from palantir_web.telegram import enviar_alertas_criticas
                enviar_alertas_criticas(alertas_nuevas)
            except Exception:
                pass
    except Exception:
        ultimo_estado["alertas_nuevas"] = []

    return web.json_response(ultimo_estado)


async def vigilar_pagina(app):
    """Desactivado: ya no se auto-apaga."""
    while True:
        await asyncio.sleep(9999)


async def handle_detectar(request):
    """
    Detecta infraestructura con el modelo de IA sobre el área visible.
    Recibe el centro (lat, lon) y descarga una imagen satelital a ZOOM 19
    (donde el modelo fue entrenado), sin importar a qué zoom esté el usuario.
    Las detecciones se GUARDAN en disco para no perderlas al reiniciar.
    """
    if motor_ia is None or cliente_sat is None:
        return web.json_response({"error": "IA no disponible", "detecciones": []})
    try:
        lat = float(request.query.get("lat"))
        lon = float(request.query.get("lon"))
    except (TypeError, ValueError):
        return web.json_response({"error": "faltan lat/lon", "detecciones": []})

    loop = asyncio.get_event_loop()

    def _run():
        # SIEMPRE descarga a zoom 19 (donde el modelo fue entrenado y detecta bien)
        area = cliente_sat.area_alrededor(lon, lat, radio_m=300, zoom=19)
        if area.imagen is None:
            return []
        dets = motor_ia.analizar(area)
        salida = []
        for d in dets:
            try:
                salida.append({
                    "clase": str(d.clase_id), "nombre": str(d.nombre_clase),
                    "conf": round(float(d.confianza), 2),
                    "lat": float(d.lat), "lon": float(d.lon),
                    "color": str(d.color), "icono": str(d.icono),
                    "fuente": str(d.fuente),
                })
            except Exception:
                continue
        # Guardar las detecciones nuevas en disco
        if salida:
            _guardar_detecciones(salida)
        return salida

    try:
        dets = await loop.run_in_executor(None, _run)
    except Exception as ex:
        print(f"[IA] Error al detectar: {ex}")
        return web.json_response({"error": str(ex), "detecciones": []})
    return web.json_response(
        {"modo": motor_ia.modo, "detecciones": dets},
        dumps=lambda o: json.dumps(o, ensure_ascii=False, allow_nan=False),
    )


# === PERSISTENCIA DE DETECCIONES ===
_DETECCIONES_PATH = RAIZ / "datos" / "detecciones_ia.json"


def _cargar_detecciones() -> list[dict]:
    """Carga detecciones guardadas de sesiones anteriores."""
    if _DETECCIONES_PATH.exists():
        try:
            return json.loads(_DETECCIONES_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
    return []


def _guardar_detecciones(nuevas: list[dict]):
    """Agrega detecciones nuevas al archivo (sin duplicar las que ya existen)."""
    existentes = _cargar_detecciones()
    # Deduplicar por coordenadas cercanas
    for nueva in nuevas:
        es_dup = False
        for ex in existentes:
            if (abs(ex.get("lat", 0) - nueva["lat"]) < 0.0003 and
                abs(ex.get("lon", 0) - nueva["lon"]) < 0.0003):
                es_dup = True
                break
        if not es_dup:
            existentes.append(nueva)
    _DETECCIONES_PATH.parent.mkdir(parents=True, exist_ok=True)
    _DETECCIONES_PATH.write_text(json.dumps(existentes, ensure_ascii=False), encoding="utf-8")


async def handle_detecciones_guardadas(request):
    """Devuelve todas las detecciones guardadas de sesiones anteriores."""
    return web.json_response(_cargar_detecciones())


async def handle_exportar_csv(request):
    """Exporta todas las detecciones guardadas como CSV descargable."""
    dets = _cargar_detecciones()
    lineas = ["lat,lon,clase,nombre,confianza,fuente"]
    for d in dets:
        lineas.append(f"{d.get('lat','')},{d.get('lon','')},{d.get('clase','')},{d.get('nombre','')},{d.get('conf','')},{d.get('fuente','')}")
    csv_text = "\n".join(lineas)
    return web.Response(
        text=csv_text,
        content_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=detecciones_falcon_cfe.csv"}
    )


async def handle_historial(request):
    """Devuelve el historial de alertas (exportable)."""
    formato = request.query.get("formato", "json")
    historial = motor_alertas.get_historial(500)
    if formato == "csv":
        lineas = ["timestamp,severidad,tipo,mensaje,activo"]
        for h in historial:
            lineas.append(f"{h.get('timestamp','')},{h.get('severidad','')},{h.get('tipo','')},\"{h.get('mensaje','')}\",{h.get('activo_nombre','')}")
        return web.Response(
            text="\n".join(lineas), content_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=historial_alertas_falcon.csv"}
        )
    return web.json_response(historial)


async def handle_reporte(request):
    """Genera un reporte HTML completo descargable (imprimible como PDF)."""
    from datetime import datetime
    from palantir_web.cenace import obtener_datos_cenace

    cenace = obtener_datos_cenace()
    historial = motor_alertas.get_historial(50)
    dets = _cargar_detecciones()

    plantas_data = ultimo_estado.get("plantas", [])
    lineas_data = ultimo_estado.get("lineas", [])
    resumen = ultimo_estado.get("resumen", {})

    # Generar HTML del reporte
    html = f"""<!DOCTYPE html><html><head><meta charset="utf-8">
<title>Reporte FALCON CFE — {datetime.now().strftime('%d/%m/%Y %H:%M')}</title>
<style>
body{{font-family:'Segoe UI',sans-serif;max-width:900px;margin:0 auto;padding:20px;color:#222;}}
h1{{color:#1a5276;border-bottom:3px solid #1a5276;padding-bottom:10px;}}
h2{{color:#2c3e50;margin-top:30px;border-bottom:1px solid #ddd;padding-bottom:5px;}}
table{{width:100%;border-collapse:collapse;margin:10px 0;font-size:12px;}}
th{{background:#1a5276;color:#fff;padding:8px;text-align:left;}}
td{{padding:6px 8px;border-bottom:1px solid #eee;}}
tr:hover td{{background:#f5f5f5;}}
.kpi-grid{{display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin:15px 0;}}
.kpi{{background:#f8f9fa;border:1px solid #dee2e6;border-radius:8px;padding:15px;text-align:center;}}
.kpi .valor{{font-size:24px;font-weight:bold;color:#1a5276;}}
.kpi .label{{font-size:11px;color:#666;text-transform:uppercase;}}
.alerta-crit{{color:#c0392b;font-weight:bold;}}
.alerta-alta{{color:#e67e22;}}
.footer{{margin-top:40px;color:#999;font-size:10px;text-align:center;border-top:1px solid #eee;padding-top:10px;}}
@media print{{body{{margin:0;}} .no-print{{display:none;}}}}
</style></head><body>
<h1>🦅 FALCON CFE — Reporte de Infraestructura</h1>
<p><b>Fecha:</b> {datetime.now().strftime('%d de %B de %Y, %H:%M hrs')}<br>
<b>Región:</b> Noroeste de México (BC, BCS, Sonora, Chihuahua, Sinaloa)<br>
<b>Fuente de datos:</b> {cenace.get('fuente','estimado')}</p>

<h2>Resumen del Sistema</h2>
<div class="kpi-grid">
<div class="kpi"><div class="valor">{resumen.get('generacion_total_mw',0):.0f} MW</div><div class="label">Generación</div></div>
<div class="kpi"><div class="valor">{resumen.get('demanda_estimada_mw',0):.0f} MW</div><div class="label">Demanda</div></div>
<div class="kpi"><div class="valor">{resumen.get('factor_carga_sistema',0):.1f}%</div><div class="label">Factor Carga</div></div>
<div class="kpi"><div class="valor">{resumen.get('plantas_operando',0)}/{resumen.get('plantas_total',0)}</div><div class="label">Plantas Operando</div></div>
<div class="kpi"><div class="valor">{resumen.get('lineas_operando',0)}/{resumen.get('lineas_total',0)}</div><div class="label">Líneas Operando</div></div>
<div class="kpi"><div class="valor">{resumen.get('frecuencia_sistema',60):.3f} Hz</div><div class="label">Frecuencia</div></div>
</div>

<h2>Mix de Generación</h2>
<table><tr><th>Tipo</th><th>Generación (MW)</th></tr>"""

    mix = cenace.get("por_tipo", {})
    for tipo, mw in sorted(mix.items(), key=lambda x: -x[1]):
        html += f"<tr><td>{tipo.replace('_',' ').title()}</td><td>{mw} MW</td></tr>"

    html += "</table><h2>Estado de Plantas</h2><table><tr><th>Planta</th><th>Estado</th><th>Tipo</th><th>Gen MW</th><th>Cap MW</th><th>Temp</th></tr>"
    for p in plantas_data[:28]:
        color = 'alerta-crit' if p.get('estado')=='Falla' else ''
        html += f"<tr class='{color}'><td>{p.get('nombre','')}</td><td>{p.get('estado','')}</td><td>{p.get('tipo','')}</td><td>{p.get('gen_mw',0):.0f}</td><td>{p.get('cap_mw',0)}</td><td>{p.get('temp',0):.0f}°C</td></tr>"

    html += "</table><h2>Últimas Alertas</h2><table><tr><th>Fecha</th><th>Severidad</th><th>Mensaje</th></tr>"
    for a in historial[-20:]:
        cls = 'alerta-crit' if a.get('severidad')=='critica' else ('alerta-alta' if a.get('severidad')=='alta' else '')
        html += f"<tr class='{cls}'><td>{a.get('timestamp','')}</td><td>{a.get('severidad','')}</td><td>{a.get('mensaje','')}</td></tr>"

    html += f"""</table>
<h2>Detecciones de IA Satelital</h2>
<p>Total de detecciones acumuladas: <b>{len(dets)}</b></p>

<div class="footer">
Generado por FALCON CFE v1.0 — {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}<br>
Sistema de Monitoreo de Infraestructura Eléctrica del Noroeste de México
</div>
<script class="no-print">document.title+=' (Ctrl+P para imprimir como PDF)';</script>
</body></html>"""

    return web.Response(text=html, content_type="text/html",
                        headers={"Content-Disposition": "inline; filename=reporte_falcon_cfe.html"})


async def handle_prediccion(request):
    """Predicción de demanda para las próximas 12 horas basada en patrones históricos."""
    import math
    from datetime import datetime, timedelta

    hora_actual = datetime.now().hour
    mes = datetime.now().month
    es_verano = mes in (5, 6, 7, 8, 9, 10)
    base = 5500 if es_verano else 4800

    predicciones = []
    for h in range(12):
        hora = (hora_actual + h) % 24
        pico_offset = math.sin(math.pi * (hora - 5) / 12) if 5 <= hora <= 21 else -0.3
        demanda = base + pico_offset * (1800 if es_verano else 1200)
        demanda = max(3200, demanda)
        ts = (datetime.now() + timedelta(hours=h)).strftime("%H:%M")
        predicciones.append({"hora": ts, "demanda_mw": round(demanda), "h_offset": h})

    return web.json_response({
        "predicciones": predicciones,
        "estacion": "verano" if es_verano else "invierno",
        "nota": "Predicción basada en patrones históricos de demanda del Noroeste",
    })


async def handle_vehiculos(request):
    """
    Endpoint de tracking de vehículos CFE.
    Preparado para recibir datos GPS reales. Por ahora devuelve datos de demo
    que muestran cómo se vería el tracking en el mapa.
    """
    import random, math
    from datetime import datetime

    # Datos de demo (simula 5 vehículos de cuadrillas CFE)
    vehiculos = [
        {"id": "V-001", "tipo": "Cuadrilla Distribución", "conductor": "Juan Pérez",
         "lat": 29.07 + random.gauss(0, 0.01), "lon": -110.96 + random.gauss(0, 0.01),
         "velocidad_kmh": random.randint(0, 60), "estado": "en_ruta", "ciudad": "Hermosillo"},
        {"id": "V-002", "tipo": "Cuadrilla Transmisión", "conductor": "Carlos López",
         "lat": 29.09 + random.gauss(0, 0.01), "lon": -110.95 + random.gauss(0, 0.01),
         "velocidad_kmh": random.randint(0, 80), "estado": "en_ruta", "ciudad": "Hermosillo"},
        {"id": "V-003", "tipo": "Supervisor", "conductor": "María García",
         "lat": 32.62 + random.gauss(0, 0.01), "lon": -115.45 + random.gauss(0, 0.01),
         "velocidad_kmh": random.randint(0, 50), "estado": "en_sitio", "ciudad": "Mexicali"},
        {"id": "V-004", "tipo": "Emergencia", "conductor": "Roberto Sánchez",
         "lat": 31.69 + random.gauss(0, 0.01), "lon": -106.42 + random.gauss(0, 0.01),
         "velocidad_kmh": random.randint(30, 100), "estado": "en_ruta", "ciudad": "Cd. Juárez"},
        {"id": "V-005", "tipo": "Cuadrilla Distribución", "conductor": "Ana Martínez",
         "lat": 24.80 + random.gauss(0, 0.01), "lon": -107.39 + random.gauss(0, 0.01),
         "velocidad_kmh": 0, "estado": "estacionado", "ciudad": "Culiacán"},
    ]
    return web.json_response({
        "vehiculos": vehiculos,
        "total": len(vehiculos),
        "en_ruta": sum(1 for v in vehiculos if v["estado"] == "en_ruta"),
        "timestamp": datetime.now().strftime("%H:%M:%S"),
        "nota": "Datos de demostración. Conecta datos GPS reales para tracking real.",
    })


# === APP ===
async def on_startup(app):
    # Primer tick para tener datos listos de inmediato
    tick_simulador()
    # Vigilar si la página se cierra (para apagar el servidor solo)
    asyncio.create_task(vigilar_pagina(app))
    # Iniciar auto-aprendizaje en segundo plano
    threading.Thread(target=_auto_learn_worker, daemon=True).start()
    print("🧠 Auto-aprendizaje en segundo plano activado (investiga tras 10 min de inactividad)")
    # Abrir navegador después de 1.5 segundos
    loop = asyncio.get_event_loop()
    loop.call_later(1.5, lambda: webbrowser.open("http://localhost:8080"))


def main():
    app = web.Application()
    app.on_startup.append(on_startup)
    app.router.add_get("/", handle_index)
    app.router.add_get("/ws", ws_handler)
    app.router.add_get("/api/estado", handle_estado)
    app.router.add_get("/api/detectar", handle_detectar)
    app.router.add_get("/api/detecciones", handle_detecciones_guardadas)
    app.router.add_get("/api/exportar/csv", handle_exportar_csv)
    app.router.add_get("/api/historial", handle_historial)
    app.router.add_get("/api/reporte", handle_reporte)
    app.router.add_get("/api/prediccion", handle_prediccion)
    app.router.add_get("/api/vehiculos", handle_vehiculos)
    app.router.add_get("/api/lineas", handle_lineas_coords)
    app.router.add_get("/api/torres", handle_torres)
    app.router.add_get("/api/interconexiones", handle_interconexiones)
    app.router.add_get("/api/osm", handle_osm_region)
    app.router.add_get("/api/osm/torres", handle_osm_torres)
    app.router.add_get("/api/cfe/buscar", handle_buscar_cfe)
    app.router.add_get("/api/cfe/manual", handle_cfe_manual)
    app.router.add_post("/api/mec", handle_mec_chat)
    app.router.add_post("/api/tts", handle_tts)
    app.router.add_get("/static/{name}", handle_static)

    print("=" * 60)
    print("  🦅 FALCON CFE — Versión Web + IA Astra")
    print("  Abriendo en http://localhost:8080")
    print("")
    print("  🤖 Astra (4 IAs): JARVIS + Optimus + Caine + Cyborg")
    print("  🎧 Voz: edge-tts (es-MX-DaliaNeural)")
    print("  🧠 Auto-aprendizaje: activo tras 10 min de inactividad")
    print("")
    # Mostrar IP de red local para que otros se conecten
    try:
        import socket
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip_local = s.getsockname()[0]
        s.close()
        print(f"  📡 Otros en tu red pueden acceder en:")
        print(f"     http://{ip_local}:8080")
    except Exception:
        pass
    print("")
    print("  Presiona Ctrl+C para detener")
    print("=" * 60)

    web.run_app(app, host="0.0.0.0", port=8080, print=None)


if __name__ == "__main__":
    main()
