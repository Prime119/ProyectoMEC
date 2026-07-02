"""
Servidor web para Palantir CFE — Backend con datos en tiempo real.

- Sirve el frontend (HTML/CSS/JS)
- WebSocket: envía telemetría cada 2 segundos a todos los clientes
- REST: endpoints para el chat MEC y datos estáticos

Ejecutar:
    python palantir_web/servidor.py

Se abre automáticamente en http://localhost:8080
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import threading
import time
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

# MEC Assistant (opcional)
mec_assistant = None
try:
    from mec_assistant import MECAssistant
    mec_assistant = MECAssistant.boot()
    print("🤖 MEC Assistant integrado")
except Exception as e:
    print(f"⚠️ MEC no disponible: {e}")


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
    """Endpoint para el chat MEC. Usa Ollama si está disponible; si no, modo reglas."""
    data = await request.json()
    texto = data.get("texto", "")

    # Intentar con el LLM (Ollama) si MEC está disponible
    if mec_assistant is not None:
        try:
            loop = asyncio.get_event_loop()
            ctx = json.dumps(ultimo_estado.get("resumen", {}), ensure_ascii=False)
            prompt = f"[INFRAESTRUCTURA CFE]\n{ctx}\n\n[PREGUNTA]\n{texto}"
            respuesta = await loop.run_in_executor(None, mec_assistant.handle, prompt)
            # Si el cerebro reportó error de Ollama, caer al modo reglas
            if respuesta and "[MEC]" in respuesta and ("Error" in respuesta or "cerebro local" in respuesta):
                respuesta = responder_por_reglas(texto)
            return web.json_response({"respuesta": respuesta})
        except Exception as e:
            print(f"[MEC] Ollama fallo: {e}")

    # Modo reglas (sin Ollama): responde con los datos del sistema
    return web.json_response({"respuesta": responder_por_reglas(texto)})


def responder_por_reglas(texto: str) -> str:
    """Responde preguntas comunes usando los datos actuales, sin necesitar LLM."""
    t = texto.lower()
    r = ultimo_estado.get("resumen", {})
    plantas = ultimo_estado.get("plantas", [])
    lineas = ultimo_estado.get("lineas", [])

    fallas = [p for p in plantas if p["estado"] == "Falla"]
    manto = [p for p in plantas if p["estado"] == "Mantenimiento"]
    lineas_falla = [l for l in lineas if l["estado"] == "Falla"]
    sobrecargadas = [l for l in lineas if l["carga"] > 85]

    if any(w in t for w in ["falla", "problema", "riesgo", "alerta", "mal"]):
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

    if any(w in t for w in ["resumen", "estado", "general", "cómo", "como esta", "situación"]):
        return (f"Sistema: {r.get('generacion_total_mw',0):.0f} MW generados, "
                f"{r.get('plantas_operando',0)}/{r.get('plantas_total',0)} plantas operando, "
                f"{r.get('lineas_operando',0)}/{r.get('lineas_total',0)} líneas activas, "
                f"frecuencia {r.get('frecuencia_sistema',60):.3f} Hz, "
                f"{r.get('alertas_activas',0)} alertas activas.")

    return ("Puedo responder sobre: generación, fallas, líneas sobrecargadas, "
            "mantenimiento o un resumen del sistema. Para respuestas más completas, "
            "instala Ollama (ollama.com) y descarga el modelo qwen2.5:3b-instruct.")


async def handle_estado(request):
    """Avanza el simulador y devuelve el estado actual (polling en tiempo real)."""
    tick_simulador()
    return web.json_response(ultimo_estado)


# === APP ===
async def on_startup(app):
    # Primer tick para tener datos listos de inmediato
    tick_simulador()
    # Abrir navegador después de 1.5 segundos
    loop = asyncio.get_event_loop()
    loop.call_later(1.5, lambda: webbrowser.open("http://localhost:8080"))


def main():
    app = web.Application()
    app.on_startup.append(on_startup)
    app.router.add_get("/", handle_index)
    app.router.add_get("/ws", ws_handler)
    app.router.add_get("/api/estado", handle_estado)
    app.router.add_get("/api/lineas", handle_lineas_coords)
    app.router.add_get("/api/torres", handle_torres)
    app.router.add_get("/api/interconexiones", handle_interconexiones)
    app.router.add_get("/api/osm", handle_osm_region)
    app.router.add_get("/api/osm/torres", handle_osm_torres)
    app.router.add_post("/api/mec", handle_mec_chat)
    app.router.add_get("/static/{name}", handle_static)

    print("=" * 60)
    print("  🦅 FALCON CFE — Versión Web")
    print("  Abriendo en http://localhost:8080")
    print("  Presiona Ctrl+C para detener")
    print("=" * 60)

    web.run_app(app, host="0.0.0.0", port=8080, print=None)


if __name__ == "__main__":
    main()
