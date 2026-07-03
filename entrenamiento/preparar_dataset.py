"""
Preparación de dataset con AUTO-ETIQUETADO desde OpenStreetMap — FALCON CFE.

Genera un dataset YOLO etiquetado AUTOMÁTICAMENTE, sin dibujar cajas a mano:

  1. Reúne activos georreferenciados de OSM (subestaciones, torres, postes,
     transformadores, generadores) + la base de datos de plantas de CFE.
  2. Para cada zona, descarga imágenes satelitales en mosaico.
  3. Proyecta las coordenadas (lat/lon) de cada activo sobre la imagen y calcula
     su caja delimitadora (bounding box) en pixeles -> etiqueta YOLO.
  4. Divide en train / val / test.

Esto "bootstrapea" un dataset real usando el conocimiento de OSM como supervisión
débil. Las etiquetas son aproximadas (dependen de la precisión de OSM y del tamaño
estimado por clase); revisarlas a mano mejora la calidad, pero ya sirven para
entrenar un primer modelo funcional.

Uso:
    pip install pillow httpx
    python entrenamiento/preparar_dataset.py --zoom 18 --max-imagenes 400

Requiere internet (satélite + Overpass).
"""
from __future__ import annotations

import argparse
import random
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from palantir_cfe.satelite import ClienteSatelital, resolucion_metros_por_pixel
from palantir_cfe.catalogo_activos import CLASE_A_INDICE, get_clase
from palantir_cfe.datos_geograficos import (
    PLANTAS_GENERACION, SUBESTACIONES, TipoPlanta,
)



# Zonas objetivo (ciudades con buena cobertura en OSM). bbox: (S, W, N, E)
ZONAS = {
    "hermosillo":  (28.98, -111.08, 29.15, -110.88),
    "mexicali":    (32.58, -115.55, 32.72, -115.38),
    "tijuana":     (32.44, -117.10, 32.56, -116.85),
    "culiacan":    (24.74, -107.46, 24.86, -107.34),
    "los_mochis":  (25.75, -109.03, 25.83, -108.94),
    "chihuahua":   (28.58, -106.15, 28.72, -106.02),
    "cd_juarez":   (31.62, -106.50, 31.78, -106.32),
    "mazatlan":    (23.19, -106.47, 23.30, -106.36),
    "la_paz":      (24.10, -110.35, 24.20, -110.26),
    "cerro_prieto":(32.36, -115.28, 32.46, -115.18),
}

# Tamaño físico típico (metros) por clase, para estimar la caja en la imagen
TAMANO_M = {
    "subestacion": 130, "termoelectrica": 300, "ciclo_combinado": 250,
    "hidroelectrica": 400, "solar": 200, "eolica": 60, "carbonifera": 350,
    "nucleoelectrica": 400, "torre_grande": 22, "torre_mediana": 16,
    "torre_chica": 10, "poste_grande": 8, "poste_mediano": 6, "poste_chico": 5,
    "transformador": 8, "linea_transmision": 40, "medidor": 2,
    "oficina_central": 60, "oficina_regional": 40, "oficina": 25,
    "centro_atencion": 30, "centro_capacitacion": 60, "cajero": 3, "almacen": 80,
}


def _clase_de_planta(p) -> str:
    if "Carbón" in p.combustible:
        return "carbonifera"
    m = {
        TipoPlanta.HIDROELECTRICA: "hidroelectrica", TipoPlanta.EOLICA: "eolica",
        TipoPlanta.TERMOELECTRICA: "termoelectrica", TipoPlanta.SOLAR: "solar",
        TipoPlanta.CICLO_COMBINADO: "ciclo_combinado", TipoPlanta.TURBOGAS: "termoelectrica",
        TipoPlanta.GEOTERMICA: "termoelectrica",
    }
    return m.get(p.tipo, "termoelectrica")


def _clase_osm(tags: dict) -> str | None:
    """Mapea tags OSM power=* a una clase del catálogo."""
    power = tags.get("power")
    if power == "substation":
        return "subestacion"
    if power == "transformer":
        return "transformador"
    if power == "pole":
        return "poste_chico"
    if power == "tower":
        v = _voltaje(tags)
        if v >= 345000:
            return "torre_grande"
        if v >= 161000:
            return "torre_mediana"
        return "torre_chica" if v else "torre_mediana"
    if power == "generator":
        src = (tags.get("generator:source") or "").lower()
        if "wind" in src:
            return "eolica"
        if "solar" in src:
            return "solar"
        return None
    return None


def _voltaje(tags: dict) -> int:
    v = tags.get("voltage", "")
    try:
        return max(int(x) for x in v.replace(";", " ").split() if x.isdigit())
    except Exception:
        return 0



def recolectar_activos(bbox, region=None, detalle=True) -> list[dict]:
    """
    Reúne activos {lat, lon, clase} de OSM y de la base de datos dentro de un bbox.

    - region: resultado ya cargado de osm.obtener_infraestructura_region() para
      NO volver a consultar OSM en cada llamada (clave para que sea rápido).
    - detalle: si True, hace UNA consulta de torres/postes para todo el bbox.
    """
    s, w, n, e = bbox
    activos = []

    # 1) Plantas y subestaciones de la base de datos propia
    for p in PLANTAS_GENERACION:
        if s <= p.lat <= n and w <= p.lon <= e:
            activos.append({"lat": p.lat, "lon": p.lon, "clase": _clase_de_planta(p)})
    for sub in SUBESTACIONES:
        if s <= sub.lat <= n and w <= sub.lon <= e:
            activos.append({"lat": sub.lat, "lon": sub.lon, "clase": "subestacion"})

    # 2) OSM región (subestaciones + generadores) — ya cargada, solo filtramos
    region = region or {}
    for sub in region.get("subestaciones", []):
        if s <= sub["lat"] <= n and w <= sub["lon"] <= e:
            activos.append({"lat": sub["lat"], "lon": sub["lon"], "clase": "subestacion"})
    for g in region.get("generadores", []):
        if s <= g["lat"] <= n and w <= g["lon"] <= e:
            cl = "eolica" if "wind" in (g.get("fuente", "").lower()) else "solar"
            activos.append({"lat": g["lat"], "lon": g["lon"], "clase": cl})

    # 3) OSM detalle (torres/postes/transformadores) — UNA consulta por zona
    if detalle:
        try:
            from palantir_web import osm
            det = osm.obtener_torres_bbox(s, w, n, e)
            for pt in det.get("puntos", []):
                cl = _clase_osm({"power": pt.get("tipo", "tower")})
                if cl:
                    activos.append({"lat": pt["lat"], "lon": pt["lon"], "clase": cl})
        except Exception as ex:
            print(f"  [OSM] detalle no disponible: {ex}")

    return activos


def _bbox_pixel(area, lon, lat, clase, mpp):
    """Calcula la caja YOLO (normalizada) de un activo sobre la imagen."""
    px, py = area.lonlat_a_pixel(lon, lat)
    if px < 0 or py < 0 or px > area.ancho_px or py > area.alto_px:
        return None
    tam_m = TAMANO_M.get(clase, 20)
    tam_px = max(8, tam_m / max(mpp, 0.05))
    cx = px / area.ancho_px
    cy = py / area.alto_px
    w = min(tam_px / area.ancho_px, 0.9)
    h = min(tam_px / area.alto_px, 0.9)
    if not (0 < cx < 1 and 0 < cy < 1):
        return None
    return (cx, cy, w, h)



def generar_dataset(salida: Path, zoom: int, max_imagenes: int,
                    radio_m: float, split=(0.7, 0.2, 0.1)):
    """Genera imágenes + etiquetas YOLO auto-etiquetadas desde OSM/DB."""
    cliente = ClienteSatelital(proveedor="esri")
    for sub in ["images/train", "images/val", "images/test",
                "labels/train", "labels/val", "labels/test"]:
        (salida / sub).mkdir(parents=True, exist_ok=True)

    # Cargar la infraestructura de OSM UNA SOLA VEZ (cacheada en disco)
    region = {}
    try:
        from palantir_web import osm
        print("Cargando infraestructura de OpenStreetMap (una vez, puede tardar)...")
        region = osm.obtener_infraestructura_region()
        print(f"  OSM región: {len(region.get('subestaciones', []))} subestaciones, "
              f"{len(region.get('generadores', []))} generadores")
    except Exception as ex:
        print(f"  [OSM] región no disponible: {ex}")

    escenas = []  # (nombre, area, etiquetas[])
    grado = radio_m / 111320.0  # paso de cuadrícula (aprox)

    for zona, bbox in ZONAS.items():
        if len(escenas) >= max_imagenes:
            break
        print(f"\n== Zona: {zona} ==")
        # UNA consulta de detalle por zona; luego todo se filtra en memoria
        activos = recolectar_activos(bbox, region=region, detalle=True)
        print(f"  {len(activos)} activos recolectados")
        if not activos:
            continue
        s, w, n, e = bbox
        lat = s
        while lat < n and len(escenas) < max_imagenes:
            lon = w
            while lon < e and len(escenas) < max_imagenes:
                cen_lat, cen_lon = lat + grado, lon + grado
                cercanos = [a for a in activos
                            if abs(a["lat"] - cen_lat) < grado and abs(a["lon"] - cen_lon) < grado]
                if cercanos:
                    esc = _crear_escena(cliente, cen_lon, cen_lat, zoom, radio_m,
                                        zona, len(escenas), activos)
                    if esc:
                        escenas.append(esc)
                        print(f"  imagen {len(escenas)}/{max_imagenes} — {len(esc[2])} etiquetas")
                lon += grado * 2
            lat += grado * 2

    print(f"\nTotal de escenas con etiquetas: {len(escenas)}")
    _guardar_escenas(escenas, salida, split)


def _crear_escena(cliente, lon, lat, zoom, radio_m, zona, idx, activos):
    """
    Descarga una imagen y genera sus etiquetas YOLO.
    Filtra la lista de activos YA recolectada (sin consultar OSM de nuevo).
    """
    area = cliente.area_alrededor(lon, lat, radio_m=radio_m, zoom=zoom)
    if area.imagen is None:
        return None
    mpp = area.metros_por_pixel()
    etiquetas = []
    for a in activos:
        # Solo los activos que caen dentro de esta imagen
        if not (area.lat_min <= a["lat"] <= area.lat_max and
                area.lon_min <= a["lon"] <= area.lon_max):
            continue
        idx_clase = CLASE_A_INDICE.get(a["clase"])
        if idx_clase is None:
            continue
        caja = _bbox_pixel(area, a["lon"], a["lat"], a["clase"], mpp)
        if caja:
            cx, cy, w, h = caja
            etiquetas.append(f"{idx_clase} {cx:.6f} {cy:.6f} {w:.6f} {h:.6f}")
    if not etiquetas:
        return None
    return (f"{zona}_{idx}", area.imagen, etiquetas)


def _guardar_escenas(escenas, salida, split):
    """Guarda imágenes y etiquetas divididas en train/val/test."""
    random.shuffle(escenas)
    n = len(escenas)
    n_train = int(n * split[0])
    n_val = int(n * split[1])
    for i, (nombre, imagen, etiquetas) in enumerate(escenas):
        parte = "train" if i < n_train else ("val" if i < n_train + n_val else "test")
        imagen.save(str(salida / "images" / parte / f"{nombre}.jpg"), quality=88)
        (salida / "labels" / parte / f"{nombre}.txt").write_text(
            "\n".join(etiquetas), encoding="utf-8")
    print(f"Guardado: {n_train} train, {n_val} val, {n - n_train - n_val} test en {salida}")


def main():
    ap = argparse.ArgumentParser(description="Auto-etiquetado de dataset satelital CFE desde OSM")
    ap.add_argument("--salida", default="./datos", help="Carpeta de salida del dataset")
    ap.add_argument("--zoom", type=int, default=18, help="Zoom satelital (17-19)")
    ap.add_argument("--radio", type=float, default=200, help="Radio (m) por imagen")
    ap.add_argument("--max-imagenes", type=int, default=400, help="Máximo de imágenes a generar")
    args = ap.parse_args()
    generar_dataset(Path(args.salida), args.zoom, args.max_imagenes, args.radio)
    print("\nSiguiente paso: python entrenamiento/generar_config.py && python entrenamiento/entrenar.py")


if __name__ == "__main__":
    main()
