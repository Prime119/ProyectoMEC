"""
Generador de Geometría 3D — Palantir CFE.

Genera mallas (meshes) y estructuras de líneas 3D con estética holográfica
(estilo "gemelo digital" / wireframe brillante) para cada tipo de estructura
de CFE. Se renderizan con pyqtgraph.opengl en vista_3d.py.

Cada función devuelve datos numpy que el visor 3D convierte en objetos GL:
- Vértices y caras (para superficies)
- Segmentos de líneas (para el wireframe holográfico)

No depende de PyQt; solo de numpy. Así se puede probar sin display.
"""
from __future__ import annotations

import math
import numpy as np
from dataclasses import dataclass, field


@dataclass
class Geometria3D:
    """Geometría lista para renderizar."""
    # Malla de superficie (opcional)
    vertices: np.ndarray | None = None        # (N, 3)
    caras: np.ndarray | None = None           # (M, 3) índices
    # Wireframe (líneas holográficas)
    lineas: list[np.ndarray] = field(default_factory=list)  # lista de (K, 3)
    color: tuple = (0.0, 0.83, 1.0, 1.0)      # cian holográfico por defecto
    altura_m: float = 50.0                    # altura para la etiqueta flotante



# =============================================================================
# PRIMITIVAS DE WIREFRAME
# =============================================================================

def _circulo(radio: float, z: float, segmentos: int = 32) -> np.ndarray:
    """Anillo horizontal a altura z."""
    ang = np.linspace(0, 2 * np.pi, segmentos + 1)
    x = radio * np.cos(ang)
    y = radio * np.sin(ang)
    zz = np.full_like(x, z)
    return np.column_stack([x, y, zz])


def _verticales(radio_base: float, radio_top: float, z0: float, z1: float,
                n: int = 12) -> list[np.ndarray]:
    """Líneas verticales que conectan dos anillos (para conos/cilindros)."""
    lineas = []
    ang = np.linspace(0, 2 * np.pi, n, endpoint=False)
    for a in ang:
        p0 = [radio_base * math.cos(a), radio_base * math.sin(a), z0]
        p1 = [radio_top * math.cos(a), radio_top * math.sin(a), z1]
        lineas.append(np.array([p0, p1]))
    return lineas


def _caja_wireframe(cx, cy, cz, ancho, largo, alto) -> list[np.ndarray]:
    """Wireframe de una caja (edificio)."""
    hx, hy = ancho / 2, largo / 2
    z0, z1 = cz, cz + alto
    esquinas_abajo = [
        [cx - hx, cy - hy, z0], [cx + hx, cy - hy, z0],
        [cx + hx, cy + hy, z0], [cx - hx, cy + hy, z0],
    ]
    esquinas_arriba = [[x, y, z1] for x, y, _ in esquinas_abajo]
    lineas = []
    # Base y techo
    lineas.append(np.array(esquinas_abajo + [esquinas_abajo[0]]))
    lineas.append(np.array(esquinas_arriba + [esquinas_arriba[0]]))
    # Aristas verticales
    for a, b in zip(esquinas_abajo, esquinas_arriba):
        lineas.append(np.array([a, b]))
    return lineas


# =============================================================================
# ESTRUCTURAS DE CFE
# =============================================================================

def torre_enfriamiento(altura: float = 100.0, radio_base: float = 40.0) -> Geometria3D:
    """
    Torre de enfriamiento hiperbólica (nucleoeléctrica / termoeléctrica).
    La forma icónica de la imagen de referencia.
    """
    lineas = []
    n_niveles = 16
    zs = np.linspace(0, altura, n_niveles)
    # Perfil hiperbólico: estrecho en el medio, ancho arriba y abajo
    radios = []
    for z in zs:
        t = z / altura
        # Hiperboloide: mínimo ~0.6 del radio en la "cintura" (t=0.7)
        r = radio_base * (0.55 + 0.45 * ((t - 0.7) ** 2) / 0.49)
        radios.append(max(r, radio_base * 0.5))
    for z, r in zip(zs, radios):
        lineas.append(_circulo(r, z, 40))
    # Verticales curvas
    n_v = 20
    ang = np.linspace(0, 2 * np.pi, n_v, endpoint=False)
    for a in ang:
        pts = [[r * math.cos(a), r * math.sin(a), z] for z, r in zip(zs, radios)]
        lineas.append(np.array(pts))
    return Geometria3D(lineas=lineas, color=(0.0, 0.83, 1.0, 1.0), altura_m=altura)


def chimenea(altura: float = 120.0, radio: float = 8.0) -> Geometria3D:
    """Chimenea alta (termoeléctrica / carboeléctrica)."""
    lineas = []
    zs = np.linspace(0, altura, 8)
    for z in zs:
        lineas.append(_circulo(radio * (1 - 0.2 * z / altura), z, 20))
    lineas += _verticales(radio, radio * 0.8, 0, altura, 8)
    return Geometria3D(lineas=lineas, color=(1.0, 0.4, 0.25, 1.0), altura_m=altura)


def aerogenerador(altura_torre: float = 90.0, radio_aspa: float = 45.0) -> Geometria3D:
    """Turbina eólica: torre + 3 aspas."""
    lineas = []
    # Torre (cilindro delgado)
    lineas += _verticales(3, 2, 0, altura_torre, 6)
    for z in np.linspace(0, altura_torre, 5):
        lineas.append(_circulo(3 * (1 - 0.3 * z / altura_torre), z, 12))
    # Buje (nacelle) y 3 aspas a 120°
    cz = altura_torre
    for k in range(3):
        a = math.radians(120 * k + 30)
        punta = [radio_aspa * math.cos(a), 0, cz + radio_aspa * math.sin(a)]
        lineas.append(np.array([[0, 0, cz], punta]))
    return Geometria3D(lineas=lineas, color=(0.0, 0.9, 1.0, 1.0), altura_m=altura_torre + radio_aspa)


def torre_transmision(altura: float = 45.0, ancho_base: float = 12.0,
                      color=(1.0, 0.09, 0.27, 1.0)) -> Geometria3D:
    """Torre de transmisión de celosía (lattice)."""
    lineas = []
    hb = ancho_base / 2
    ht = ancho_base * 0.15
    # 4 patas que convergen
    base = [[-hb, -hb, 0], [hb, -hb, 0], [hb, hb, 0], [-hb, hb, 0]]
    top = [[-ht, -ht, altura], [ht, -ht, altura], [ht, ht, altura], [-ht, ht, altura]]
    for b, t in zip(base, top):
        lineas.append(np.array([b, t]))
    # Anillos horizontales (celosía)
    for frac in [0, 0.3, 0.6, 0.85, 1.0]:
        z = altura * frac
        s = hb + (ht - hb) * frac
        anillo = [[-s, -s, z], [s, -s, z], [s, s, z], [-s, s, z], [-s, -s, z]]
        lineas.append(np.array(anillo))
    # Crucetas (brazos) arriba
    for zc in [altura * 0.8, altura]:
        lineas.append(np.array([[-ancho_base, 0, zc], [ancho_base, 0, zc]]))
    return Geometria3D(lineas=lineas, color=color, altura_m=altura)


def poste(altura: float = 15.0, color=(1.0, 0.67, 0.25, 1.0)) -> Geometria3D:
    """Poste de transmisión/distribución (mástil simple con crucetas)."""
    lineas = []
    lineas.append(np.array([[0, 0, 0], [0, 0, altura]]))
    # Crucetas
    for zc in [altura * 0.85, altura]:
        lineas.append(np.array([[-3, 0, zc], [3, 0, zc]]))
    return Geometria3D(lineas=lineas, color=color, altura_m=altura)



def panel_solar(filas: int = 4, cols: int = 6, tam: float = 8.0) -> Geometria3D:
    """Arreglo de paneles solares fotovoltaicos (rejilla inclinada)."""
    lineas = []
    sep = tam * 1.5
    for i in range(filas):
        for j in range(cols):
            x0 = j * sep
            y0 = i * sep
            # Panel inclinado (borde bajo al frente, alto atrás)
            p = [
                [x0, y0, 0], [x0 + tam, y0, 0],
                [x0 + tam, y0 + tam, tam * 0.5], [x0, y0 + tam, tam * 0.5],
                [x0, y0, 0],
            ]
            lineas.append(np.array(p))
    return Geometria3D(lineas=lineas, color=(1.0, 0.84, 0.0, 1.0), altura_m=tam)


def presa_hidro(ancho: float = 120.0, altura: float = 40.0) -> Geometria3D:
    """Cortina de presa hidroeléctrica (muro curvo con embalse)."""
    lineas = []
    # Muro curvo (arco)
    ang = np.linspace(-0.6, 0.6, 20)
    radio = ancho
    top = [[radio * math.sin(a), radio * math.cos(a) - radio + 20, altura] for a in ang]
    bot = [[radio * math.sin(a), radio * math.cos(a) - radio + 20, 0] for a in ang]
    lineas.append(np.array(top))
    lineas.append(np.array(bot))
    for t, b in zip(top[::3], bot[::3]):
        lineas.append(np.array([b, t]))
    return Geometria3D(lineas=lineas, color=(0.16, 0.47, 1.0, 1.0), altura_m=altura)


def subestacion_3d(ancho: float = 60.0, largo: float = 40.0) -> Geometria3D:
    """Patio de subestación: barras horizontales sobre estructuras."""
    lineas = []
    n = 4
    alto = 12.0
    for i in range(n):
        x = i * (ancho / n)
        # Estructura vertical (pórtico)
        lineas.append(np.array([[x, 0, 0], [x, 0, alto]]))
        lineas.append(np.array([[x, largo, 0], [x, largo, alto]]))
        # Barra horizontal (bus)
        lineas.append(np.array([[x, 0, alto], [x, largo, alto]]))
    # Marco perimetral
    lineas.append(np.array([[0, 0, 0], [ancho, 0, 0], [ancho, largo, 0], [0, largo, 0], [0, 0, 0]]))
    return Geometria3D(lineas=lineas, color=(0.0, 0.83, 1.0, 1.0), altura_m=alto)


def edificio(ancho: float = 30.0, largo: float = 25.0, alto: float = 20.0,
             color=(0.25, 0.77, 1.0, 1.0)) -> Geometria3D:
    """Edificio genérico (oficina, almacén, centro)."""
    lineas = _caja_wireframe(0, 0, 0, ancho, largo, alto)
    # Líneas de "pisos" para dar sensación de escala
    n_pisos = max(2, int(alto / 4))
    for k in range(1, n_pisos):
        z = alto * k / n_pisos
        lineas.append(_circulo_rect(ancho, largo, z))
    return Geometria3D(lineas=lineas, color=color, altura_m=alto)


def _circulo_rect(ancho, largo, z):
    """Rectángulo horizontal a altura z (para pisos de edificios)."""
    hx, hy = ancho / 2, largo / 2
    return np.array([
        [-hx, -hy, z], [hx, -hy, z], [hx, hy, z], [-hx, hy, z], [-hx, -hy, z]
    ])


# =============================================================================
# MAPEO: clase del catálogo -> generador de geometría 3D
# =============================================================================

def geometria_para_clase(clase_id: str) -> Geometria3D:
    """Devuelve la geometría 3D adecuada para una clase de activo del catálogo."""
    generadores = {
        "nucleoelectrica": lambda: torre_enfriamiento(110, 45),
        "termoelectrica": lambda: _combinar([torre_enfriamiento(80, 32), chimenea(120, 8)]),
        "carbonifera": lambda: _combinar([chimenea(140, 10), edificio(50, 40, 25, (0.47, 0.33, 0.28, 1.0))]),
        "ciclo_combinado": lambda: _combinar([chimenea(70, 6), edificio(40, 30, 18, (1.0, 0.57, 0.0, 1.0))]),
        "eolica": lambda: aerogenerador(90, 45),
        "solar": lambda: panel_solar(4, 6, 8),
        "hidroelectrica": lambda: presa_hidro(120, 40),
        "subestacion": lambda: subestacion_3d(60, 40),
        "torre_grande": lambda: torre_transmision(50, 14, (1.0, 0.09, 0.27, 1.0)),
        "torre_mediana": lambda: torre_transmision(35, 10, (1.0, 0.57, 0.0, 1.0)),
        "torre_chica": lambda: torre_transmision(20, 7, (1.0, 0.84, 0.0, 1.0)),
        "poste_grande": lambda: poste(22, (1.0, 0.43, 0.25, 1.0)),
        "poste_mediano": lambda: poste(14, (1.0, 0.67, 0.25, 1.0)),
        "poste_chico": lambda: poste(9, (1.0, 0.82, 0.5, 1.0)),
        "transformador": lambda: edificio(6, 5, 5, (0.49, 0.30, 1.0, 1.0)),
        "oficina_central": lambda: edificio(40, 30, 45, (0.25, 0.77, 1.0, 1.0)),
        "oficina_regional": lambda: edificio(30, 25, 28, (0.09, 1.0, 1.0, 1.0)),
        "oficina": lambda: edificio(22, 18, 18, (0.52, 1.0, 1.0, 1.0)),
        "centro_atencion": lambda: edificio(20, 16, 10, (0.41, 0.94, 0.68, 1.0)),
        "centro_capacitacion": lambda: edificio(45, 30, 14, (0.73, 0.96, 0.79, 1.0)),
        "cajero": lambda: edificio(2, 2, 3, (0.8, 1.0, 0.56, 1.0)),
        "almacen": lambda: edificio(60, 40, 14, (1.0, 0.67, 0.25, 1.0)),
        "medidor": lambda: edificio(1, 1, 2, (0.7, 1.0, 0.35, 1.0)),
        "linea_transmision": lambda: torre_transmision(45, 14),
    }
    gen = generadores.get(clase_id, lambda: edificio(20, 20, 15))
    return gen()


def _combinar(geometrias: list[Geometria3D]) -> Geometria3D:
    """Combina varias geometrías en una sola (desplazando en X para no encimar)."""
    lineas = []
    offset = 0.0
    color = geometrias[0].color
    alt = 0.0
    for g in geometrias:
        for ln in g.lineas:
            desplazada = ln.copy()
            desplazada[:, 0] += offset
            lineas.append(desplazada)
        offset += 60.0
        alt = max(alt, g.altura_m)
    return Geometria3D(lineas=lineas, color=color, altura_m=alt)
