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
    return web.FileResponse(Path(__file__).parent / "static" / "index.html")


async def handle_static(request):
    name = request.match_info["name"]
    path = Path(__file__).parent / "static" / name
    if path.exists():
        return web.FileResponse(path)
    return web.Response(status=404)


async def handle_lineas_coords(request):
    return web.json_response(LINEAS_COORDS)


async def handle_mec_chat(request):
    """Endpoint para el chat MEC."""
    data = await request.json()
    texto = data.get("texto", "")
    if not mec_assistant:
        return web.json_response({"respuesta": "MEC no disponible. Instala Ollama."})
    # Inyectar contexto
    ctx = json.dumps(ultimo_estado.get("resumen", {}), ensure_ascii=False)
    prompt = f"[INFRAESTRUCTURA CFE]\n{ctx}\n\n[PREGUNTA]\n{texto}"
    respuesta = mec_assistant.handle(prompt)
    return web.json_response({"respuesta": respuesta})


# === APP ===
async def on_startup(app):
    asyncio.create_task(broadcast_loop())
    # Abrir navegador después de 1 segundo
    loop = asyncio.get_event_loop()
    loop.call_later(1.5, lambda: webbrowser.open("http://localhost:8080"))


def main():
    app = web.Application()
    app.on_startup.append(on_startup)
    app.router.add_get("/", handle_index)
    app.router.add_get("/ws", ws_handler)
    app.router.add_get("/api/lineas", handle_lineas_coords)
    app.router.add_post("/api/mec", handle_mec_chat)
    app.router.add_get("/static/{name}", handle_static)

    print("=" * 60)
    print("  🌐 PALANTIR CFE — Versión Web")
    print("  Abriendo en http://localhost:8080")
    print("  Presiona Ctrl+C para detener")
    print("=" * 60)

    web.run_app(app, host="0.0.0.0", port=8080, print=None)


if __name__ == "__main__":
    main()
