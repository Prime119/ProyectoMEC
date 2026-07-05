"""
Buscador de instalaciones CFE en OpenStreetMap — FALCON.

Busca oficinas, centros de atención, almacenes y cualquier edificio
etiquetado como operado por CFE. Equivale a buscar "CFE" en Google Maps,
pero gratis y sin API key.

Usa dos estrategias:
1. Overpass: busca por operator=CFE (encuentra lo que está bien etiquetado)
2. Nominatim: busca por nombre "CFE" o "Comisión Federal de Electricidad"
   (encuentra lo que Google Maps encontraría)
"""
from __future__ import annotations

import json
import time
from pathlib import Path

CACHE_DIR = Path(__file__).resolve().parent / "cache_osm"
CACHE_DIR.mkdir(parents=True, exist_ok=True)


def buscar_instalaciones_cfe(s: float, w: float, n: float, e: float) -> list[dict]:
    """
    Busca TODAS las instalaciones de CFE en un área (no solo eléctricas):
    oficinas, centros de atención, almacenes, sucursales, cajeros, etc.

    Combina Overpass (operator=CFE) + Nominatim (nombre "CFE").
    Cachea los resultados por zona.
    """
    clave = f"cfe_all_{round(s,2)}_{round(w,2)}_{round(n,2)}_{round(e,2)}.json"
    cache = CACHE_DIR / clave
    if cache.exists() and time.time() - cache.stat().st_mtime < 7 * 86400:
        try:
            return json.loads(cache.read_text(encoding="utf-8"))
        except Exception:
            pass

    resultados = []

    # 1. Overpass: todo lo que tenga operator=CFE o name con "CFE"
    try:
        from .osm import _consultar_overpass
        bbox = f"{s},{w},{n},{e}"
        query = f"""
        [out:json][timeout:60];
        (
          nwr["operator"~"CFE|Comisi[oó]n Federal",i]({bbox});
          nwr["name"~"CFE|Comisi[oó]n Federal",i]({bbox});
        );
        out center;
        """
        data = _consultar_overpass(query, timeout=65)
        for el in data.get("elements", []):
            tags = el.get("tags", {})
            lat = el.get("lat") or (el.get("center", {}) or {}).get("lat")
            lon = el.get("lon") or (el.get("center", {}) or {}).get("lon")
            if not lat or not lon:
                continue
            # Determinar el tipo de instalación
            tipo = _clasificar_instalacion(tags)
            nombre = tags.get("name", tags.get("operator", "CFE"))
            resultados.append({
                "lat": lat, "lon": lon,
                "nombre": nombre, "tipo": tipo,
                "direccion": tags.get("addr:street", ""),
                "fuente": "osm",
            })
    except Exception as ex:
        print(f"[Buscar CFE] Overpass error: {ex}")

    # 2. Nominatim: búsqueda por texto (como Google Maps)
    try:
        import httpx
        for q in ["CFE oficina", "CFE subestacion", "CFE centro atencion"]:
            url = "https://nominatim.openstreetmap.org/search"
            params = {
                "q": q, "format": "json", "limit": 50, "countrycodes": "mx",
                "viewbox": f"{w},{n},{e},{s}", "bounded": 1,
            }
            r = httpx.get(url, params=params, timeout=15,
                          headers={"User-Agent": "FALCON-CFE/1.0"})
            if r.status_code == 200:
                for item in r.json():
                    lat2 = float(item.get("lat", 0))
                    lon2 = float(item.get("lon", 0))
                    if lat2 and lon2:
                        # Evitar duplicados cercanos
                        if not any(abs(r2["lat"] - lat2) < 0.001 and abs(r2["lon"] - lon2) < 0.001
                                   for r2 in resultados):
                            resultados.append({
                                "lat": lat2, "lon": lon2,
                                "nombre": item.get("display_name", "CFE")[:80],
                                "tipo": _clasificar_por_nombre(item.get("display_name", "")),
                                "direccion": "",
                                "fuente": "nominatim",
                            })
            time.sleep(1.1)  # Nominatim pide 1 req/seg
    except Exception as ex:
        print(f"[Buscar CFE] Nominatim error: {ex}")

    # Deduplicar
    vistos = set()
    unicos = []
    for r in resultados:
        key = (round(r["lat"], 4), round(r["lon"], 4))
        if key not in vistos:
            vistos.add(key)
            unicos.append(r)

    cache.write_text(json.dumps(unicos, ensure_ascii=False), encoding="utf-8")
    print(f"[Buscar CFE] {len(unicos)} instalaciones encontradas en el área")
    return unicos


def _clasificar_instalacion(tags: dict) -> str:
    """Clasifica un elemento OSM como tipo de instalación CFE."""
    power = tags.get("power", "")
    office = tags.get("office", "")
    amenity = tags.get("amenity", "")
    building = tags.get("building", "")
    shop = tags.get("shop", "")
    name = (tags.get("name", "") + " " + tags.get("description", "")).lower()

    if power == "substation":
        return "subestacion"
    if power == "plant":
        return "planta"
    if power:
        return "infraestructura_electrica"
    if "oficina" in name or office:
        return "oficina"
    if "atencion" in name or "atención" in name or "sucursal" in name:
        return "centro_atencion"
    if "almacen" in name or "almacén" in name or building == "warehouse":
        return "almacen"
    if "capacitacion" in name or "capacitación" in name:
        return "centro_capacitacion"
    if amenity == "atm" or "cajero" in name:
        return "cajero"
    return "instalacion_cfe"


def _clasificar_por_nombre(display_name: str) -> str:
    """Clasifica resultado de Nominatim por su nombre."""
    n = display_name.lower()
    if "subestacion" in n or "subestación" in n:
        return "subestacion"
    if "oficina" in n:
        return "oficina"
    if "atencion" in n or "atención" in n or "sucursal" in n:
        return "centro_atencion"
    if "almacen" in n or "almacén" in n:
        return "almacen"
    return "instalacion_cfe"
