"""
Integración con OpenStreetMap (Overpass API) — FALCON CFE.

Importa infraestructura eléctrica REAL ya mapeada en OpenStreetMap para la región
Noroeste de México: subestaciones, plantas de generación, líneas de transmisión,
torres y postes.

En México la red eléctrica de transmisión es operada por CFE, así que toda la
infraestructura `power=*` de la región corresponde esencialmente a activos CFE.

Estrategia (para no saturar):
- Infraestructura regional (subestaciones, plantas, líneas): se consulta una vez
  para toda la región y se cachea en disco.
- Torres y postes (miles): se consultan por área visible (bbox) solo al acercar,
  y se cachean por zona.

Requiere: httpx e internet. Si falla, devuelve listas vacías sin romper nada.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

# Bounding box de la región Noroeste (S, W, N, E)
REGION_BBOX = (22.0, -118.5, 33.6, -104.5)

OVERPASS_URLS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
]

CACHE_DIR = Path(__file__).resolve().parent / "cache_osm"
CACHE_DIR.mkdir(parents=True, exist_ok=True)


def _consultar_overpass(query: str, timeout: float = 90.0) -> dict:
    """Ejecuta una consulta Overpass. Prueba varios servidores. Devuelve JSON."""
    try:
        import httpx
    except ImportError:
        print("[OSM] httpx no instalado. pip install httpx")
        return {"elements": []}

    for url in OVERPASS_URLS:
        try:
            r = httpx.post(url, data={"data": query}, timeout=timeout,
                           headers={"User-Agent": "FALCON-CFE/1.0"})
            if r.status_code == 200:
                return r.json()
        except Exception as e:
            print(f"[OSM] Error con {url}: {e}")
    return {"elements": []}



def _centro_de_elemento(el: dict):
    """Obtiene lat/lon representativo de un elemento OSM."""
    if "lat" in el and "lon" in el:
        return el["lat"], el["lon"]
    if "center" in el:
        return el["center"]["lat"], el["center"]["lon"]
    if "geometry" in el and el["geometry"]:
        pts = el["geometry"]
        return sum(p["lat"] for p in pts) / len(pts), sum(p["lon"] for p in pts) / len(pts)
    return None


def obtener_infraestructura_region(refrescar: bool = False) -> dict:
    """
    Obtiene subestaciones, plantas y líneas de toda la región (cacheado).
    Devuelve {"subestaciones": [...], "plantas": [...], "lineas": [...]}.
    """
    cache = CACHE_DIR / "region_mx.json"
    if cache.exists() and not refrescar:
        # Cache válido por 30 días
        if time.time() - cache.stat().st_mtime < 30 * 86400:
            try:
                return json.loads(cache.read_text(encoding="utf-8"))
            except Exception:
                pass

    s, w, n, e = REGION_BBOX
    bbox = f"{s},{w},{n},{e}"
    query = f"""
    [out:json][timeout:120];
    area["ISO3166-1"="MX"][admin_level=2]->.mx;
    (
      nwr["power"="substation"](area.mx)({bbox});
      nwr["power"="plant"](area.mx)({bbox});
      way["power"="line"](area.mx)({bbox});
    );
    out geom;
    """
    data = _consultar_overpass(query)
    resultado = {"subestaciones": [], "plantas": [], "lineas": []}

    for el in data.get("elements", []):
        tags = el.get("tags", {})
        power = tags.get("power")
        nombre = tags.get("name", tags.get("operator", ""))
        if power == "line":
            geom = el.get("geometry")
            if geom and len(geom) >= 2:
                coords = [[p["lat"], p["lon"]] for p in geom]
                resultado["lineas"].append({
                    "nombre": nombre or "Línea",
                    "coords": coords,
                    "voltaje": tags.get("voltage", ""),
                })
        else:
            c = _centro_de_elemento(el)
            if not c:
                continue
            item = {"nombre": nombre, "lat": c[0], "lon": c[1],
                    "voltaje": tags.get("voltage", ""),
                    "operador": tags.get("operator", "")}
            if power == "substation":
                resultado["subestaciones"].append(item)
            elif power == "plant":
                item["fuente"] = tags.get("plant:source", tags.get("generator:source", ""))
                resultado["plantas"].append(item)

    cache.write_text(json.dumps(resultado, ensure_ascii=False), encoding="utf-8")
    print(f"[OSM] Región: {len(resultado['subestaciones'])} subestaciones, "
          f"{len(resultado['plantas'])} plantas, {len(resultado['lineas'])} líneas")
    return resultado



def obtener_torres_bbox(s: float, w: float, n: float, e: float) -> list[dict]:
    """
    Obtiene torres y postes eléctricos dentro de un bounding box (para zoom cercano).
    Cacheado por zona redondeada para reutilizar consultas.
    """
    # Limitar tamaño del área para no pedir demasiado (máx ~0.5° por lado)
    if (n - s) > 0.6 or (e - w) > 0.6:
        cy, cx = (s + n) / 2, (w + e) / 2
        s, n = cy - 0.3, cy + 0.3
        w, e = cx - 0.3, cx + 0.3

    # Clave de cache redondeada a 0.1°
    clave = f"torres_mx_{round(s,1)}_{round(w,1)}_{round(n,1)}_{round(e,1)}.json"
    cache = CACHE_DIR / clave
    if cache.exists() and time.time() - cache.stat().st_mtime < 7 * 86400:
        try:
            return json.loads(cache.read_text(encoding="utf-8"))
        except Exception:
            pass

    bbox = f"{s},{w},{n},{e}"
    query = f"""
    [out:json][timeout:50];
    area["ISO3166-1"="MX"][admin_level=2]->.mx;
    (
      node["power"="tower"](area.mx)({bbox});
      node["power"="pole"](area.mx)({bbox});
    );
    out;
    """
    data = _consultar_overpass(query, timeout=55)
    torres = []
    for el in data.get("elements", []):
        tags = el.get("tags", {})
        torres.append({
            "lat": el.get("lat"), "lon": el.get("lon"),
            "tipo": tags.get("power", "tower"),  # tower | pole
        })
    torres = [t for t in torres if t["lat"] and t["lon"]]
    cache.write_text(json.dumps(torres, ensure_ascii=False), encoding="utf-8")
    return torres
