"""
Catálogo de Activos CFE — Taxonomía completa para detección satelital con IA.

Define todas las clases de infraestructura que el sistema de visión debe detectar
y geolocalizar a partir de imágenes satelitales. Cada clase incluye:
- Nombre y categoría
- Color de visualización en el mapa/overlay
- Firma visual típica (para guiar al modelo de detección)
- Tamaño aproximado en metros (ayuda a filtrar detecciones por escala)
- Prioridad de monitoreo
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class CategoriaActivo(Enum):
    GENERACION = "Generación"
    TRANSMISION = "Transmisión"
    DISTRIBUCION = "Distribución"
    ADMINISTRATIVO = "Administrativo"
    COMERCIAL = "Comercial / Atención"
    LOGISTICA = "Logística"
    MEDICION = "Medición"


@dataclass
class ClaseActivo:
    """Una clase de activo detectable por el sistema de visión IA."""
    id: str                       # ID de clase para el modelo (ej. "torre_grande")
    nombre: str                   # Nombre legible
    categoria: CategoriaActivo
    color: str                    # Color hex para overlay
    firma_visual: str             # Descripción de cómo se ve desde satélite
    tamaño_min_m: float           # Tamaño mínimo aproximado (metros)
    tamaño_max_m: float           # Tamaño máximo aproximado (metros)
    prioridad: int = 3            # 1=crítico, 2=alto, 3=normal
    icono: str = "●"              # Símbolo para UI



# =============================================================================
# CATÁLOGO COMPLETO DE CLASES DETECTABLES
# =============================================================================

CATALOGO: dict[str, ClaseActivo] = {
    # === GENERACIÓN ===
    "hidroelectrica": ClaseActivo(
        "hidroelectrica", "Hidroeléctrica", CategoriaActivo.GENERACION,
        "#2979ff", "Presa/cortina de concreto, embalse de agua, casa de máquinas al pie",
        100, 2000, prioridad=1, icono="🌊"),
    "eolica": ClaseActivo(
        "eolica", "Central Eólica", CategoriaActivo.GENERACION,
        "#00e5ff", "Aerogeneradores blancos en fila, sombras largas de aspas, patrón disperso",
        50, 5000, prioridad=2, icono="🌀"),
    "termoelectrica": ClaseActivo(
        "termoelectrica", "Termoeléctrica", CategoriaActivo.GENERACION,
        "#ff5252", "Chimeneas altas, tanques de combustible, patios industriales, humo",
        200, 1500, prioridad=1, icono="🔥"),
    "solar": ClaseActivo(
        "solar", "Central Solar FV", CategoriaActivo.GENERACION,
        "#ffd600", "Grandes rejillas azul oscuro/negro de paneles alineados, muy geométrico",
        100, 10000, prioridad=2, icono="☀️"),
    "nucleoelectrica": ClaseActivo(
        "nucleoelectrica", "Nucleoeléctrica", CategoriaActivo.GENERACION,
        "#e040fb", "Domos de contención cilíndricos, torres de enfriamiento hiperbólicas",
        300, 2000, prioridad=1, icono="⚛️"),
    "ciclo_combinado": ClaseActivo(
        "ciclo_combinado", "Ciclo Combinado", CategoriaActivo.GENERACION,
        "#ff9100", "Turbinas de gas + recuperadores de calor, chimeneas medianas, compacto",
        150, 1200, prioridad=1, icono="🏭"),
    "carbonifera": ClaseActivo(
        "carbonifera", "Carboeléctrica", CategoriaActivo.GENERACION,
        "#795548", "Grandes pilas de carbón oscuro, banda transportadora, chimeneas masivas",
        300, 2000, prioridad=1, icono="⚫"),

    # === TRANSMISIÓN ===
    "subestacion": ClaseActivo(
        "subestacion", "Subestación", CategoriaActivo.TRANSMISION,
        "#00d4ff", "Patio con arreglo de barras metálicas, transformadores, cercado rectangular",
        50, 500, prioridad=1, icono="⚡"),
    "torre_grande": ClaseActivo(
        "torre_grande", "Torre de Transmisión Grande (400kV+)", CategoriaActivo.TRANSMISION,
        "#ff1744", "Torre de acero alta (>40m), base ancha, sombra larga, líneas gruesas",
        15, 50, prioridad=2, icono="🗼"),
    "torre_mediana": ClaseActivo(
        "torre_mediana", "Torre de Transmisión Mediana (230kV)", CategoriaActivo.TRANSMISION,
        "#ff9100", "Torre de acero media (20-40m), estructura reticulada visible",
        10, 30, prioridad=3, icono="📡"),
    "torre_chica": ClaseActivo(
        "torre_chica", "Torre de Transmisión Chica (115kV-)", CategoriaActivo.TRANSMISION,
        "#ffd600", "Estructura ligera o poste alto (<20m), sombra corta",
        5, 20, prioridad=3, icono="📍"),
    "linea_transmision": ClaseActivo(
        "linea_transmision", "Línea de Transmisión", CategoriaActivo.TRANSMISION,
        "#00e676", "Corredor recto despejado con torres alineadas, brecha en vegetación",
        100, 100000, prioridad=2, icono="〰️"),
    "transformador": ClaseActivo(
        "transformador", "Transformador", CategoriaActivo.TRANSMISION,
        "#7c4dff", "Bloque rectangular con aletas de enfriamiento, radiadores laterales",
        2, 15, prioridad=2, icono="🔲"),

    # === DISTRIBUCIÓN / MEDICIÓN ===
    "medidor": ClaseActivo(
        "medidor", "Medidor / Punto de Medición", CategoriaActivo.MEDICION,
        "#b2ff59", "Gabinete pequeño en poste o muro, difícil de ver, cerca de acometidas",
        0.3, 2, prioridad=3, icono="🔢"),

    # === ADMINISTRATIVO ===
    "oficina_central": ClaseActivo(
        "oficina_central", "Oficinas Centrales", CategoriaActivo.ADMINISTRATIVO,
        "#40c4ff", "Edificio corporativo grande, estacionamiento amplio, logo CFE, urbano",
        40, 300, prioridad=2, icono="🏢"),
    "oficina_regional": ClaseActivo(
        "oficina_regional", "Oficina Regional", CategoriaActivo.ADMINISTRATIVO,
        "#18ffff", "Edificio mediano de oficinas, estacionamiento, en ciudad principal",
        25, 150, prioridad=3, icono="🏬"),
    "oficina": ClaseActivo(
        "oficina", "Oficina", CategoriaActivo.ADMINISTRATIVO,
        "#84ffff", "Edificio de oficinas estándar, presencia urbana",
        15, 100, prioridad=3, icono="🏢"),

    # === COMERCIAL / ATENCIÓN ===
    "centro_atencion": ClaseActivo(
        "centro_atencion", "Centro de Atención a Clientes", CategoriaActivo.COMERCIAL,
        "#69f0ae", "Local comercial con acceso público, estacionamiento de visitantes",
        15, 120, prioridad=3, icono="🎫"),
    "centro_capacitacion": ClaseActivo(
        "centro_capacitacion", "Centro de Capacitación", CategoriaActivo.COMERCIAL,
        "#b9f6ca", "Complejo tipo campus/escuela, aulas, áreas de práctica",
        30, 400, prioridad=3, icono="🎓"),
    "cajero": ClaseActivo(
        "cajero", "Cajero Automático CFE", CategoriaActivo.COMERCIAL,
        "#ccff90", "Módulo/kiosco pequeño en fachada o interior, muy pequeño",
        0.5, 3, prioridad=3, icono="🏧"),

    # === LOGÍSTICA ===
    "almacen": ClaseActivo(
        "almacen", "Almacén", CategoriaActivo.LOGISTICA,
        "#ffab40", "Nave industrial grande, techo metálico, patio de maniobras, contenedores",
        30, 500, prioridad=3, icono="📦"),
}


def clases_por_categoria(categoria: CategoriaActivo) -> list[ClaseActivo]:
    """Devuelve todas las clases de una categoría."""
    return [c for c in CATALOGO.values() if c.categoria == categoria]


def get_clase(clase_id: str) -> ClaseActivo | None:
    """Obtiene una clase por su ID."""
    return CATALOGO.get(clase_id)


def todas_las_clases() -> list[ClaseActivo]:
    """Lista completa de clases detectables."""
    return list(CATALOGO.values())


def clases_criticas() -> list[ClaseActivo]:
    """Clases de prioridad crítica (1)."""
    return [c for c in CATALOGO.values() if c.prioridad == 1]


# Mapeo de índice de clase (para modelos de detección tipo YOLO)
CLASES_ORDENADAS = list(CATALOGO.keys())
CLASE_A_INDICE = {cid: i for i, cid in enumerate(CLASES_ORDENADAS)}
INDICE_A_CLASE = {i: cid for i, cid in enumerate(CLASES_ORDENADAS)}
NUM_CLASES = len(CLASES_ORDENADAS)
