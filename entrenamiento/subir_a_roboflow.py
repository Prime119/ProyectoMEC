"""
Selecciona y prepara las mejores imágenes del dataset para etiquetar en Roboflow.

De las ~2000 imágenes auto-etiquetadas, selecciona las que tienen más infraestructura
visible (subestaciones, plantas solares, etc.) y las copia a una carpeta lista para
subir a Roboflow. Así no pierdes tiempo etiquetando imágenes de terreno vacío.

Uso:
    python entrenamiento/subir_a_roboflow.py --max 600 --salida datos/para_etiquetar

Luego sube la carpeta resultante a Roboflow.com y dibuja las cajas.
"""
from __future__ import annotations

import argparse
import shutil
from pathlib import Path
from collections import Counter


def seleccionar_mejores(dataset_dir: Path, salida: Path, max_imgs: int):
    """Selecciona imágenes con más etiquetas y mayor diversidad de clases."""
    salida.mkdir(parents=True, exist_ok=True)

    # Buscar todas las imágenes con sus etiquetas
    imagenes = []
    for parte in ["train", "val", "test"]:
        img_dir = dataset_dir / "images" / parte
        lbl_dir = dataset_dir / "labels" / parte
        if not img_dir.exists():
            continue
        for img in img_dir.glob("*.jpg"):
            lbl = lbl_dir / img.with_suffix(".txt").name
            if lbl.exists():
                texto = lbl.read_text(encoding="utf-8").strip()
                lineas = [l for l in texto.split("\n") if l.strip()]
                clases = [int(l.split()[0]) for l in lineas if l.split()]
                imagenes.append({
                    "img": img, "lbl": lbl,
                    "n_etiquetas": len(lineas),
                    "n_clases": len(set(clases)),
                    "clases": clases,
                })

    if not imagenes:
        print("❌ No se encontraron imágenes en", dataset_dir)
        return

    # Ordenar por: diversidad de clases (desc) + número de etiquetas (desc)
    imagenes.sort(key=lambda x: (x["n_clases"], x["n_etiquetas"]), reverse=True)

    # Seleccionar las mejores hasta max_imgs
    seleccionadas = imagenes[:max_imgs]

    # Estadísticas
    total_etiquetas = sum(x["n_etiquetas"] for x in seleccionadas)
    todas_clases = Counter()
    for x in seleccionadas:
        todas_clases.update(x["clases"])

    print(f"Seleccionadas {len(seleccionadas)}/{len(imagenes)} imágenes con más infraestructura")
    print(f"Total de etiquetas (cajas existentes): {total_etiquetas}")
    print(f"Clases representadas: {len(todas_clases)}")
    print()

    # Copiar a la carpeta de salida (sin estructura train/val, Roboflow la divide solo)
    for i, x in enumerate(seleccionadas):
        shutil.copy2(x["img"], salida / x["img"].name)
        # También copiar las etiquetas actuales (como referencia, Roboflow las puede importar)
        shutil.copy2(x["lbl"], salida / x["lbl"].name)

    print(f"✅ {len(seleccionadas)} imágenes + etiquetas copiadas a: {salida}")
    print()
    print("=" * 60)
    print("SIGUIENTE PASO: Subir a Roboflow para etiquetar con cajas finas")
    print("=" * 60)
    print()
    print("1. Ve a https://app.roboflow.com → Crear Nuevo Proyecto")
    print("   - Tipo: Object Detection")
    print("   - Nombre: FALCON-CFE-Satelital")
    print()
    print("2. Arrastra la carpeta completa de imágenes:")
    print(f"   {salida}")
    print()
    print("3. Al subir, Roboflow detectará los .txt de etiquetas e importará")
    print("   las cajas existentes. Así NO empiezas de cero:")
    print("   ya tienes cajas aproximadas que solo necesitas AJUSTAR/DIVIDIR.")
    print()
    print("4. Clases a usar (en este orden, sin cambiar los números):")
    clases_nombres = [
        "hidroelectrica", "eolica", "termoelectrica", "solar",
        "nucleoelectrica", "ciclo_combinado", "carbonifera", "subestacion",
        "torre_grande", "torre_mediana", "torre_chica", "linea_transmision",
        "transformador", "poste_grande", "poste_mediano", "poste_chico",
        "medidor", "oficina_central", "oficina_regional", "oficina",
        "centro_atencion", "centro_capacitacion", "cajero", "almacen",
    ]
    for i, c in enumerate(clases_nombres):
        print(f"   {i:2d}  {c}")
    print()
    print("5. Dibuja las cajas sobre CADA SECCIÓN individual:")
    print("   - Cada FILA de paneles solares → una caja 'solar'")
    print("   - Cada SECCIÓN de barras de la subestación → una caja 'subestacion'")
    print("   - Cada transformador visible → una caja 'transformador'")
    print("   - Cada torre → una caja 'torre_mediana' o 'torre_grande'")
    print()
    print("6. Cuando termines (o cada 100 imágenes), exporta en formato YOLO.")
    print("   Roboflow te da un link de descarga. Ese link va al Colab para entrenar.")


def main():
    ap = argparse.ArgumentParser(description="Selecciona imágenes para etiquetar en Roboflow")
    ap.add_argument("--dataset", default="./datos", help="Carpeta del dataset actual")
    ap.add_argument("--salida", default="./datos/para_etiquetar", help="Carpeta de salida")
    ap.add_argument("--max", type=int, default=600, help="Máximo de imágenes a seleccionar")
    args = ap.parse_args()
    seleccionar_mejores(Path(args.dataset), Path(args.salida), args.max)


if __name__ == "__main__":
    main()
