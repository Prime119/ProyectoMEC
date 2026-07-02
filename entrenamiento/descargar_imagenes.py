"""
Descargador de imágenes satelitales para armar el dataset — Palantir CFE.

Descarga recortes satelitales georreferenciados de las ubicaciones CONOCIDAS
de CFE (plantas y subestaciones de la base de datos) para que sirvan como base
de etiquetado. Estas imágenes reales son el punto de partida para entrenar el
modelo: solo faltará dibujarles las cajas (bounding boxes).

Uso:
    python entrenamiento/descargar_imagenes.py --zoom 18 --salida ./datos/raw
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from palantir_cfe.datos_geograficos import PLANTAS_GENERACION, SUBESTACIONES
from palantir_cfe.satelite import ClienteSatelital


def descargar(salida: str, zoom: int, radio_m: float, proveedor: str):
    cliente = ClienteSatelital(proveedor=proveedor)
    dir_salida = Path(salida)
    dir_salida.mkdir(parents=True, exist_ok=True)

    objetivos = []
    for p in PLANTAS_GENERACION:
        objetivos.append((p.id, p.nombre, p.lon, p.lat))
    for s in SUBESTACIONES:
        objetivos.append((s.id, s.nombre, s.lon, s.lat))

    print(f"Descargando {len(objetivos)} ubicaciones (zoom={zoom}, radio={radio_m}m)...")
    ok = 0
    for aid, nombre, lon, lat in objetivos:
        try:
            area = cliente.area_alrededor(lon, lat, radio_m=radio_m, zoom=zoom)
            if area.imagen is not None:
                archivo = dir_salida / f"{aid}.jpg"
                area.imagen.save(str(archivo), quality=90)
                # Guardar georreferencia (para reconvertir cajas a lon/lat después)
                meta = dir_salida / f"{aid}.txt"
                meta.write_text(
                    f"lon_min={area.lon_min}\nlat_min={area.lat_min}\n"
                    f"lon_max={area.lon_max}\nlat_max={area.lat_max}\n"
                    f"zoom={area.zoom}\nancho_px={area.ancho_px}\nalto_px={area.alto_px}\n"
                    f"tile_x_min={area.tile_x_min}\ntile_y_min={area.tile_y_min}\n",
                    encoding="utf-8"
                )
                ok += 1
                print(f"  ✅ {nombre}")
            else:
                print(f"  ⚠️ Sin imagen: {nombre} (instala pillow + httpx)")
        except Exception as e:
            print(f"  ❌ {nombre}: {e}")

    print(f"\nListo: {ok}/{len(objetivos)} imágenes en {dir_salida}")
    print("Siguiente paso: etiqueta las imágenes con Roboflow/CVAT/LabelImg.")


def main():
    ap = argparse.ArgumentParser(description="Descarga imágenes satelitales para el dataset CFE")
    ap.add_argument("--salida", default="./datos/raw", help="Carpeta de salida")
    ap.add_argument("--zoom", type=int, default=18, help="Nivel de zoom (17-19 recomendado)")
    ap.add_argument("--radio", type=float, default=400, help="Radio en metros alrededor del punto")
    ap.add_argument("--proveedor", default="esri", choices=["esri", "google_sat"])
    args = ap.parse_args()
    descargar(args.salida, args.zoom, args.radio, args.proveedor)


if __name__ == "__main__":
    main()
