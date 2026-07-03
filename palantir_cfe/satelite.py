"""
Módulo de Imágenes Satelitales — Palantir CFE.

Descarga y georreferencia imágenes satelitales para el análisis de infraestructura.

Usa Esri World Imagery (dominio público, sin API key), servido como teselas (tiles)
en proyección Web Mercator (EPSG:3857), el estándar de mapas web.

Provee:
- Matemática de teselas (tile math): lat/lon <-> índice de tesela <-> pixel
- Descarga y cacheo de teselas
- Composición de un mosaico para un área (bounding box)
- Georreferenciación exacta: convertir un pixel de la imagen a coordenadas reales
"""
from __future__ import annotations

import math
import os
import io
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

# Proveedores de teselas satelitales (dominio público / sin API key)
PROVEEDORES = {
    "esri": {
        "nombre": "Esri World Imagery",
        "url": "https://server.arcgisonline.com/ArcGIS/rest/services/"
               "World_Imagery/MapServer/tile/{z}/{y}/{x}",
        "attribution": "Esri, Maxar, Earthstar Geographics",
        "max_zoom": 19,
    },
    "google_sat": {
        "nombre": "Google Satellite",
        "url": "https://mt1.google.com/vt/lyrs=s&x={x}&y={y}&z={z}",
        "attribution": "Google",
        "max_zoom": 20,
    },
}

TILE_SIZE = 256  # Tamaño estándar de tesela en pixeles



# =============================================================================
# MATEMÁTICA DE TESELAS (Web Mercator / EPSG:3857)
# =============================================================================

def lonlat_a_tile(lon: float, lat: float, z: int) -> tuple[float, float]:
    """Convierte lon/lat a coordenadas de tesela (fraccionarias) en zoom z."""
    lat_rad = math.radians(lat)
    n = 2.0 ** z
    x = (lon + 180.0) / 360.0 * n
    y = (1.0 - math.asinh(math.tan(lat_rad)) / math.pi) / 2.0 * n
    return x, y


def tile_a_lonlat(x: float, y: float, z: int) -> tuple[float, float]:
    """Convierte coordenadas de tesela (fraccionarias) a lon/lat."""
    n = 2.0 ** z
    lon = x / n * 360.0 - 180.0
    lat_rad = math.atan(math.sinh(math.pi * (1 - 2 * y / n)))
    lat = math.degrees(lat_rad)
    return lon, lat


def resolucion_metros_por_pixel(lat: float, z: int) -> float:
    """Metros por pixel a una latitud y zoom dados (para estimar tamaños)."""
    return 156543.03392 * math.cos(math.radians(lat)) / (2 ** z)


@dataclass
class AreaSatelital:
    """
    Un mosaico satelital georreferenciado de un área.

    Permite convertir cualquier pixel (px, py) del mosaico a lon/lat exactos,
    lo cual es la base para geolocalizar detecciones de IA.
    """
    lon_min: float
    lat_min: float
    lon_max: float
    lat_max: float
    zoom: int
    ancho_px: int
    alto_px: int
    tile_x_min: int
    tile_y_min: int
    imagen: Optional[object] = None  # PIL.Image si está disponible

    def pixel_a_lonlat(self, px: float, py: float) -> tuple[float, float]:
        """Convierte un pixel del mosaico a coordenadas geográficas exactas."""
        tile_x = self.tile_x_min + px / TILE_SIZE
        tile_y = self.tile_y_min + py / TILE_SIZE
        return tile_a_lonlat(tile_x, tile_y, self.zoom)

    def lonlat_a_pixel(self, lon: float, lat: float) -> tuple[float, float]:
        """Convierte coordenadas geográficas a un pixel del mosaico."""
        tx, ty = lonlat_a_tile(lon, lat, self.zoom)
        px = (tx - self.tile_x_min) * TILE_SIZE
        py = (ty - self.tile_y_min) * TILE_SIZE
        return px, py

    def metros_por_pixel(self) -> float:
        """Resolución del mosaico en metros por pixel (a la latitud central)."""
        lat_centro = (self.lat_min + self.lat_max) / 2
        return resolucion_metros_por_pixel(lat_centro, self.zoom)



# =============================================================================
# DESCARGA Y COMPOSICIÓN DE MOSAICOS
# =============================================================================

class ClienteSatelital:
    """Descarga teselas satelitales y compone mosaicos georreferenciados."""

    def __init__(self, proveedor: str = "esri", cache_dir: str | None = None):
        if proveedor not in PROVEEDORES:
            proveedor = "esri"
        self.proveedor = PROVEEDORES[proveedor]
        self.proveedor_id = proveedor
        # Cache local de teselas
        base = Path(cache_dir) if cache_dir else Path(__file__).resolve().parent / "cache_tiles"
        self.cache_dir = base
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _url_tesela(self, x: int, y: int, z: int) -> str:
        return self.proveedor["url"].format(x=x, y=y, z=z)

    def _ruta_cache(self, x: int, y: int, z: int) -> Path:
        d = self.cache_dir / self.proveedor_id / str(z) / str(x)
        d.mkdir(parents=True, exist_ok=True)
        return d / f"{y}.jpg"

    def _descargar_tesela(self, x: int, y: int, z: int, reintentos: int = 3) -> Optional[bytes]:
        """
        Descarga una tesela (con cache), con reintentos y espera creciente.
        Si el proveedor actual falla, prueba con los demás proveedores como respaldo.
        Así una imagen no queda incompleta por un tropiezo puntual del servidor.
        """
        ruta = self._ruta_cache(x, y, z)
        if ruta.exists():
            return ruta.read_bytes()
        try:
            import httpx
        except ImportError:
            return None
        import time as _t
        headers = {"User-Agent": "FALCON-CFE/1.0 (infraestructura CFE)"}
        # Orden de proveedores: primero el elegido, luego los demás como respaldo
        proveedores = [self.proveedor["url"]] + [
            p["url"] for k, p in PROVEEDORES.items() if k != self.proveedor_id
        ]
        for intento in range(reintentos):
            for plantilla in proveedores:
                try:
                    url = plantilla.format(x=x, y=y, z=z)
                    r = httpx.get(url, headers=headers, timeout=15.0 + intento * 10)
                    if r.status_code == 200 and r.content:
                        ruta.write_bytes(r.content)
                        return r.content
                except Exception:
                    pass
            _t.sleep(1 + intento)  # espera creciente antes de reintentar
        print(f"[Satélite] No se pudo descargar la tesela {z}/{x}/{y} tras {reintentos} intentos")
        return None

    def obtener_area(self, lon_min: float, lat_min: float,
                     lon_max: float, lat_max: float, zoom: int = 16) -> AreaSatelital:
        """
        Descarga y compone un mosaico satelital para un bounding box.

        Retorna un AreaSatelital con la imagen (si PIL está disponible) y toda
        la información de georreferenciación.
        """
        zoom = min(zoom, self.proveedor["max_zoom"])

        # Teselas que cubren el área
        x0, y0 = lonlat_a_tile(lon_min, lat_max, zoom)  # esquina superior izq
        x1, y1 = lonlat_a_tile(lon_max, lat_min, zoom)  # esquina inferior der
        tile_x_min, tile_x_max = int(math.floor(x0)), int(math.floor(x1))
        tile_y_min, tile_y_max = int(math.floor(y0)), int(math.floor(y1))

        n_x = tile_x_max - tile_x_min + 1
        n_y = tile_y_max - tile_y_min + 1
        ancho = n_x * TILE_SIZE
        alto = n_y * TILE_SIZE

        # Recalcular los bounds reales del mosaico completo
        lon_min_r, lat_max_r = tile_a_lonlat(tile_x_min, tile_y_min, zoom)
        lon_max_r, lat_min_r = tile_a_lonlat(tile_x_max + 1, tile_y_max + 1, zoom)

        area = AreaSatelital(
            lon_min=lon_min_r, lat_min=lat_min_r,
            lon_max=lon_max_r, lat_max=lat_max_r,
            zoom=zoom, ancho_px=ancho, alto_px=alto,
            tile_x_min=tile_x_min, tile_y_min=tile_y_min,
        )

        # Componer mosaico si PIL está disponible
        try:
            from PIL import Image
            mosaico = Image.new("RGB", (ancho, alto), (10, 14, 23))
            for ix in range(n_x):
                for iy in range(n_y):
                    tx = tile_x_min + ix
                    ty = tile_y_min + iy
                    data = self._descargar_tesela(tx, ty, zoom)
                    if data:
                        try:
                            tile_img = Image.open(io.BytesIO(data)).convert("RGB")
                            mosaico.paste(tile_img, (ix * TILE_SIZE, iy * TILE_SIZE))
                        except Exception:
                            pass
            area.imagen = mosaico
        except ImportError:
            print("[Satélite] Pillow (PIL) no instalado — no se compone imagen. "
                  "Instala: pip install pillow")

        return area

    def area_alrededor(self, lon: float, lat: float,
                       radio_m: float = 500, zoom: int = 17) -> AreaSatelital:
        """Obtiene un área satelital centrada en un punto con un radio en metros."""
        # Grados aproximados por metro
        grados_lat = radio_m / 111320.0
        grados_lon = radio_m / (111320.0 * math.cos(math.radians(lat)))
        return self.obtener_area(
            lon - grados_lon, lat - grados_lat,
            lon + grados_lon, lat + grados_lat, zoom
        )
