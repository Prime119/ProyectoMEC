"""
Base de datos geográfica de infraestructura CFE — Noroeste de México.

Contiene información real de:
- Centrales de generación (termoeléctrica, ciclo combinado, geotérmica, solar, eólica)
- Subestaciones eléctricas principales
- Líneas de transmisión (230kV y 400kV)
- Coordenadas geográficas reales

Fuentes: Reportes públicos de CFE, CENACE, PRODESEN, CRE.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class TipoPlanta(Enum):
    TERMOELECTRICA = "Termoeléctrica"
    CICLO_COMBINADO = "Ciclo Combinado"
    GEOTERMICA = "Geotérmica"
    SOLAR = "Solar Fotovoltaica"
    EOLICA = "Eólica"
    TURBOGAS = "Turbogás"
    HIDROELECTRICA = "Hidroeléctrica"


class EstadoMX(Enum):
    BAJA_CALIFORNIA = "Baja California"
    BAJA_CALIFORNIA_SUR = "Baja California Sur"
    SONORA = "Sonora"
    CHIHUAHUA = "Chihuahua"
    SINALOA = "Sinaloa"


class EstadoOperativo(Enum):
    OPERANDO = "Operando"
    MANTENIMIENTO = "Mantenimiento"
    FALLA = "Falla"
    FUERA_LINEA = "Fuera de Línea"
    ARRANQUE = "Arranque"


class NivelTension(Enum):
    KV_115 = "115 kV"
    KV_230 = "230 kV"
    KV_400 = "400 kV"


@dataclass
class CentralGeneracion:
    """Planta de generación eléctrica."""
    id: str
    nombre: str
    tipo: TipoPlanta
    estado: EstadoMX
    municipio: str
    lat: float
    lon: float
    capacidad_mw: float          # Capacidad instalada en MW
    unidades: int                # Número de unidades generadoras
    combustible: str = ""        # Gas natural, carbón, geotérmico, solar, viento
    año_operacion: int = 0
    propietario: str = "CFE"


@dataclass
class Subestacion:
    """Subestación eléctrica."""
    id: str
    nombre: str
    estado: EstadoMX
    lat: float
    lon: float
    nivel_tension: NivelTension
    capacidad_mva: float
    tipo: str = "Transmisión"    # Transmisión | Distribución | Maniobras


@dataclass
class LineaTransmision:
    """Línea de transmisión entre dos puntos."""
    id: str
    nombre: str
    origen_id: str               # ID de subestación/planta origen
    destino_id: str              # ID de subestación/planta destino
    nivel_tension: NivelTension
    longitud_km: float
    capacidad_mw: float
    circuitos: int = 1
    estados_cruza: list[str] = field(default_factory=list)


# =============================================================================
# DATOS DE INFRAESTRUCTURA REAL DE CFE — NOROESTE DE MÉXICO
# =============================================================================

PLANTAS_GENERACION: list[CentralGeneracion] = [
    # === BAJA CALIFORNIA ===
    CentralGeneracion(
        id="BC-CC-RPBC", nombre="CC Presidente Juárez (Rosarito)",
        tipo=TipoPlanta.CICLO_COMBINADO, estado=EstadoMX.BAJA_CALIFORNIA,
        municipio="Tijuana", lat=32.3433, lon=-117.0311,
        capacidad_mw=1094, unidades=6, combustible="Gas Natural", año_operacion=2004
    ),
    CentralGeneracion(
        id="BC-GEO-CERRO", nombre="Geotermoeléctrica Cerro Prieto",
        tipo=TipoPlanta.GEOTERMICA, estado=EstadoMX.BAJA_CALIFORNIA,
        municipio="Mexicali", lat=32.4142, lon=-115.2342,
        capacidad_mw=570, unidades=13, combustible="Geotérmico", año_operacion=1973
    ),
    CentralGeneracion(
        id="BC-CC-MEXICALI", nombre="CC La Rosita (Mexicali)",
        tipo=TipoPlanta.CICLO_COMBINADO, estado=EstadoMX.BAJA_CALIFORNIA,
        municipio="Mexicali", lat=32.5928, lon=-115.4267,
        capacidad_mw=1100, unidades=4, combustible="Gas Natural", año_operacion=2003
    ),
    CentralGeneracion(
        id="BC-SOL-RUMOROSA", nombre="Solar Fotovoltaica Rumorosa",
        tipo=TipoPlanta.SOLAR, estado=EstadoMX.BAJA_CALIFORNIA,
        municipio="Tecate", lat=32.5417, lon=-116.4333,
        capacidad_mw=41, unidades=1, combustible="Solar", año_operacion=2018
    ),
    CentralGeneracion(
        id="BC-EOL-ENERGÍA", nombre="Parque Eólico Energía Sierra Juárez",
        tipo=TipoPlanta.EOLICA, estado=EstadoMX.BAJA_CALIFORNIA,
        municipio="Tecate", lat=32.5850, lon=-116.2667,
        capacidad_mw=155, unidades=47, combustible="Viento", año_operacion=2015
    ),
    CentralGeneracion(
        id="BC-TG-TIJUANA", nombre="Turbogás Tijuana",
        tipo=TipoPlanta.TURBOGAS, estado=EstadoMX.BAJA_CALIFORNIA,
        municipio="Tijuana", lat=32.4800, lon=-116.9200,
        capacidad_mw=320, unidades=4, combustible="Gas Natural", año_operacion=2001
    ),

    # === BAJA CALIFORNIA SUR ===
    CentralGeneracion(
        id="BCS-TE-PUNTA", nombre="Termoeléctrica Punta Prieta",
        tipo=TipoPlanta.TERMOELECTRICA, estado=EstadoMX.BAJA_CALIFORNIA_SUR,
        municipio="La Paz", lat=24.1867, lon=-110.0800,
        capacidad_mw=113, unidades=3, combustible="Combustóleo", año_operacion=1990
    ),
    CentralGeneracion(
        id="BCS-CC-BCS1", nombre="CC Baja California Sur I",
        tipo=TipoPlanta.CICLO_COMBINADO, estado=EstadoMX.BAJA_CALIFORNIA_SUR,
        municipio="La Paz", lat=24.1583, lon=-110.0917,
        capacidad_mw=42, unidades=2, combustible="Gas Natural", año_operacion=2014
    ),
    CentralGeneracion(
        id="BCS-SOL-COMONDU", nombre="Solar Fotovoltaica Comondú",
        tipo=TipoPlanta.SOLAR, estado=EstadoMX.BAJA_CALIFORNIA_SUR,
        municipio="Comondú", lat=25.0500, lon=-111.6600,
        capacidad_mw=30, unidades=1, combustible="Solar", año_operacion=2019
    ),
    CentralGeneracion(
        id="BCS-TE-CABO", nombre="Termoeléctrica Los Cabos",
        tipo=TipoPlanta.TERMOELECTRICA, estado=EstadoMX.BAJA_CALIFORNIA_SUR,
        municipio="Los Cabos", lat=23.0333, lon=-109.7167,
        capacidad_mw=89, unidades=4, combustible="Combustóleo/Diésel", año_operacion=2005
    ),

    # === SONORA ===
    CentralGeneracion(
        id="SON-CC-HERMOSILLO", nombre="CC Hermosillo",
        tipo=TipoPlanta.CICLO_COMBINADO, estado=EstadoMX.SONORA,
        municipio="Hermosillo", lat=29.0328, lon=-110.9000,
        capacidad_mw=253, unidades=3, combustible="Gas Natural", año_operacion=2001
    ),
    CentralGeneracion(
        id="SON-CC-GUAYMAS", nombre="CC Guaymas II",
        tipo=TipoPlanta.CICLO_COMBINADO, estado=EstadoMX.SONORA,
        municipio="Guaymas", lat=27.9350, lon=-110.8900,
        capacidad_mw=234, unidades=2, combustible="Gas Natural", año_operacion=1982
    ),
    CentralGeneracion(
        id="SON-CC-OBREGON", nombre="CC Ciudad Obregón",
        tipo=TipoPlanta.CICLO_COMBINADO, estado=EstadoMX.SONORA,
        municipio="Cajeme", lat=27.4833, lon=-109.9333,
        capacidad_mw=375, unidades=3, combustible="Gas Natural", año_operacion=2004
    ),
    CentralGeneracion(
        id="SON-CC-AGUA", nombre="CC Agua Prieta II",
        tipo=TipoPlanta.CICLO_COMBINADO, estado=EstadoMX.SONORA,
        municipio="Agua Prieta", lat=31.3267, lon=-109.5489,
        capacidad_mw=544, unidades=3, combustible="Gas Natural", año_operacion=2011
    ),
    CentralGeneracion(
        id="SON-TE-EMPALME", nombre="Termoeléctrica Empalme (Guaymas I)",
        tipo=TipoPlanta.TERMOELECTRICA, estado=EstadoMX.SONORA,
        municipio="Empalme", lat=27.9500, lon=-110.8167,
        capacidad_mw=324, unidades=4, combustible="Combustóleo", año_operacion=1972
    ),
    CentralGeneracion(
        id="SON-SOL-PRIETO", nombre="Solar Fotovoltaica Puerto Libertad",
        tipo=TipoPlanta.SOLAR, estado=EstadoMX.SONORA,
        municipio="Pitiquito", lat=29.9100, lon=-112.6700,
        capacidad_mw=339, unidades=1, combustible="Solar", año_operacion=2018
    ),
    CentralGeneracion(
        id="SON-TE-NACOZARI", nombre="Carboeléctrica Nacozari (Plutarco Elías Calles)",
        tipo=TipoPlanta.TERMOELECTRICA, estado=EstadoMX.SONORA,
        municipio="Nacozari de García", lat=30.3667, lon=-109.6667,
        capacidad_mw=630, unidades=2, combustible="Carbón", año_operacion=1981
    ),

    # === CHIHUAHUA ===
    CentralGeneracion(
        id="CHI-CC-CHIHUAHUA", nombre="CC Chihuahua III",
        tipo=TipoPlanta.CICLO_COMBINADO, estado=EstadoMX.CHIHUAHUA,
        municipio="Chihuahua", lat=28.6400, lon=-106.1000,
        capacidad_mw=619, unidades=3, combustible="Gas Natural", año_operacion=2007
    ),
    CentralGeneracion(
        id="CHI-CC-JUAREZ", nombre="CC Samalayuca II",
        tipo=TipoPlanta.CICLO_COMBINADO, estado=EstadoMX.CHIHUAHUA,
        municipio="Juárez", lat=31.3350, lon=-106.4800,
        capacidad_mw=516, unidades=2, combustible="Gas Natural", año_operacion=1998
    ),
    CentralGeneracion(
        id="CHI-TE-SAMALAYUCA", nombre="Termoeléctrica Samalayuca",
        tipo=TipoPlanta.TERMOELECTRICA, estado=EstadoMX.CHIHUAHUA,
        municipio="Juárez", lat=31.3500, lon=-106.4667,
        capacidad_mw=316, unidades=2, combustible="Gas Natural", año_operacion=1985
    ),
    CentralGeneracion(
        id="CHI-SOL-CHUAHUA", nombre="Solar Fotovoltaica Ahumada",
        tipo=TipoPlanta.SOLAR, estado=EstadoMX.CHIHUAHUA,
        municipio="Ahumada", lat=30.5833, lon=-106.5000,
        capacidad_mw=100, unidades=1, combustible="Solar", año_operacion=2020
    ),
    CentralGeneracion(
        id="CHI-EOL-JUAREZ", nombre="Parque Eólico Juárez",
        tipo=TipoPlanta.EOLICA, estado=EstadoMX.CHIHUAHUA,
        municipio="Juárez", lat=31.6000, lon=-106.4000,
        capacidad_mw=60, unidades=20, combustible="Viento", año_operacion=2016
    ),

    # === SINALOA ===
    CentralGeneracion(
        id="SIN-TE-TOPOLOBAMPO", nombre="Termoeléctrica Topolobampo",
        tipo=TipoPlanta.TERMOELECTRICA, estado=EstadoMX.SINALOA,
        municipio="Ahome", lat=25.6000, lon=-109.0500,
        capacidad_mw=320, unidades=2, combustible="Combustóleo", año_operacion=1987
    ),
    CentralGeneracion(
        id="SIN-CC-TOPII", nombre="CC Topolobampo II",
        tipo=TipoPlanta.CICLO_COMBINADO, estado=EstadoMX.SINALOA,
        municipio="Ahome", lat=25.5900, lon=-109.0400,
        capacidad_mw=575, unidades=3, combustible="Gas Natural", año_operacion=2006
    ),
    CentralGeneracion(
        id="SIN-CC-MAZATLAN", nombre="CC Mazatlán (José Aceves Pozos)",
        tipo=TipoPlanta.CICLO_COMBINADO, estado=EstadoMX.SINALOA,
        municipio="Mazatlán", lat=23.2494, lon=-106.4111,
        capacidad_mw=513, unidades=3, combustible="Gas Natural", año_operacion=2003
    ),
    CentralGeneracion(
        id="SIN-HID-HUMAYA", nombre="Hidroeléctrica Humaya (Sanalona)",
        tipo=TipoPlanta.HIDROELECTRICA, estado=EstadoMX.SINALOA,
        municipio="Culiacán", lat=24.8000, lon=-107.0833,
        capacidad_mw=14, unidades=2, combustible="Hidráulico", año_operacion=1948
    ),
    CentralGeneracion(
        id="SIN-HID-FUERTE", nombre="Hidroeléctrica El Fuerte (Huites)",
        tipo=TipoPlanta.HIDROELECTRICA, estado=EstadoMX.SINALOA,
        municipio="Choix", lat=26.8400, lon=-108.3800,
        capacidad_mw=422, unidades=2, combustible="Hidráulico", año_operacion=1996
    ),
    CentralGeneracion(
        id="SIN-SOL-MOCHIS", nombre="Solar Fotovoltaica Los Mochis",
        tipo=TipoPlanta.SOLAR, estado=EstadoMX.SINALOA,
        municipio="Ahome", lat=25.7500, lon=-108.9800,
        capacidad_mw=108, unidades=1, combustible="Solar", año_operacion=2021
    ),
]


SUBESTACIONES: list[Subestacion] = [
    # === BAJA CALIFORNIA ===
    Subestacion("SUB-BC-TIJUANA", "SE Tijuana", EstadoMX.BAJA_CALIFORNIA, 32.5149, -117.0382, NivelTension.KV_230, 750),
    Subestacion("SUB-BC-MEXICALI", "SE Mexicali Oriente", EstadoMX.BAJA_CALIFORNIA, 32.6245, -115.4523, NivelTension.KV_230, 600),
    Subestacion("SUB-BC-ENSENADA", "SE Ensenada", EstadoMX.BAJA_CALIFORNIA, 31.8667, -116.5964, NivelTension.KV_230, 400),
    Subestacion("SUB-BC-CERROPRIETO", "SE Cerro Prieto", EstadoMX.BAJA_CALIFORNIA, 32.4000, -115.2300, NivelTension.KV_230, 800),

    # === BAJA CALIFORNIA SUR ===
    Subestacion("SUB-BCS-LAPAZ", "SE La Paz", EstadoMX.BAJA_CALIFORNIA_SUR, 24.1426, -110.3128, NivelTension.KV_115, 200),
    Subestacion("SUB-BCS-CABOS", "SE Los Cabos", EstadoMX.BAJA_CALIFORNIA_SUR, 23.0500, -109.7000, NivelTension.KV_115, 150),

    # === SONORA ===
    Subestacion("SUB-SON-HERMOSILLO", "SE Hermosillo", EstadoMX.SONORA, 29.0728, -110.9600, NivelTension.KV_400, 1200),
    Subestacion("SUB-SON-NACOZARI", "SE Nacozari", EstadoMX.SONORA, 30.3700, -109.6800, NivelTension.KV_400, 900),
    Subestacion("SUB-SON-GUAYMAS", "SE Guaymas", EstadoMX.SONORA, 27.9200, -110.9000, NivelTension.KV_230, 600),
    Subestacion("SUB-SON-NOGALES", "SE Nogales", EstadoMX.SONORA, 31.3300, -110.9300, NivelTension.KV_230, 400),
    Subestacion("SUB-SON-OBREGON", "SE Obregón", EstadoMX.SONORA, 27.4900, -109.9400, NivelTension.KV_230, 500),

    # === CHIHUAHUA ===
    Subestacion("SUB-CHI-CHIHUAHUA", "SE Chihuahua", EstadoMX.CHIHUAHUA, 28.6353, -106.0889, NivelTension.KV_400, 1000),
    Subestacion("SUB-CHI-JUAREZ", "SE Juárez", EstadoMX.CHIHUAHUA, 31.6904, -106.4245, NivelTension.KV_400, 800),
    Subestacion("SUB-CHI-DELICIAS", "SE Delicias", EstadoMX.CHIHUAHUA, 28.1900, -105.4700, NivelTension.KV_230, 400),
    Subestacion("SUB-CHI-SAMALAYUCA", "SE Samalayuca", EstadoMX.CHIHUAHUA, 31.3500, -106.4800, NivelTension.KV_400, 700),

    # === SINALOA ===
    Subestacion("SUB-SIN-MOCHIS", "SE Los Mochis", EstadoMX.SINALOA, 25.7872, -108.9856, NivelTension.KV_230, 600),
    Subestacion("SUB-SIN-CULIACAN", "SE Culiacán", EstadoMX.SINALOA, 24.7994, -107.3938, NivelTension.KV_230, 700),
    Subestacion("SUB-SIN-MAZATLAN", "SE Mazatlán", EstadoMX.SINALOA, 23.2417, -106.4100, NivelTension.KV_230, 500),
    Subestacion("SUB-SIN-TOPOLOBAMPO", "SE Topolobampo", EstadoMX.SINALOA, 25.6000, -109.0500, NivelTension.KV_230, 600),
]


LINEAS_TRANSMISION: list[LineaTransmision] = [
    # === LÍNEAS 400 kV (Troncales) ===
    LineaTransmision(
        "LT-400-NACO-HERM", "Nacozari - Hermosillo 400kV",
        "SUB-SON-NACOZARI", "SUB-SON-HERMOSILLO",
        NivelTension.KV_400, 280, 1200, 2, ["Sonora"]
    ),
    LineaTransmision(
        "LT-400-HERM-CHI", "Hermosillo - Chihuahua 400kV",
        "SUB-SON-HERMOSILLO", "SUB-CHI-CHIHUAHUA",
        NivelTension.KV_400, 620, 1000, 1, ["Sonora", "Chihuahua"]
    ),
    LineaTransmision(
        "LT-400-JUAREZ-SAM", "Juárez - Samalayuca 400kV",
        "SUB-CHI-JUAREZ", "SUB-CHI-SAMALAYUCA",
        NivelTension.KV_400, 45, 1500, 2, ["Chihuahua"]
    ),
    LineaTransmision(
        "LT-400-NACO-JUAREZ", "Nacozari - Juárez 400kV",
        "SUB-SON-NACOZARI", "SUB-CHI-JUAREZ",
        NivelTension.KV_400, 440, 1000, 1, ["Sonora", "Chihuahua"]
    ),

    # === LÍNEAS 230 kV (Regionales) ===
    LineaTransmision(
        "LT-230-TIJ-ENS", "Tijuana - Ensenada 230kV",
        "SUB-BC-TIJUANA", "SUB-BC-ENSENADA",
        NivelTension.KV_230, 108, 400, 2, ["Baja California"]
    ),
    LineaTransmision(
        "LT-230-TIJ-MEX", "Tijuana - Mexicali 230kV",
        "SUB-BC-TIJUANA", "SUB-BC-MEXICALI",
        NivelTension.KV_230, 185, 500, 2, ["Baja California"]
    ),
    LineaTransmision(
        "LT-230-CERRO-MEX", "Cerro Prieto - Mexicali 230kV",
        "SUB-BC-CERROPRIETO", "SUB-BC-MEXICALI",
        NivelTension.KV_230, 35, 600, 2, ["Baja California"]
    ),
    LineaTransmision(
        "LT-230-HERM-GUAY", "Hermosillo - Guaymas 230kV",
        "SUB-SON-HERMOSILLO", "SUB-SON-GUAYMAS",
        NivelTension.KV_230, 130, 400, 2, ["Sonora"]
    ),
    LineaTransmision(
        "LT-230-GUAY-OBRE", "Guaymas - Obregón 230kV",
        "SUB-SON-GUAYMAS", "SUB-SON-OBREGON",
        NivelTension.KV_230, 110, 400, 2, ["Sonora"]
    ),
    LineaTransmision(
        "LT-230-NOG-HERM", "Nogales - Hermosillo 230kV",
        "SUB-SON-NOGALES", "SUB-SON-HERMOSILLO",
        NivelTension.KV_230, 270, 400, 1, ["Sonora"]
    ),
    LineaTransmision(
        "LT-230-OBRE-MOCH", "Obregón - Los Mochis 230kV",
        "SUB-SON-OBREGON", "SUB-SIN-MOCHIS",
        NivelTension.KV_230, 200, 400, 2, ["Sonora", "Sinaloa"]
    ),
    LineaTransmision(
        "LT-230-MOCH-CUL", "Los Mochis - Culiacán 230kV",
        "SUB-SIN-MOCHIS", "SUB-SIN-CULIACAN",
        NivelTension.KV_230, 215, 400, 2, ["Sinaloa"]
    ),
    LineaTransmision(
        "LT-230-CUL-MAZ", "Culiacán - Mazatlán 230kV",
        "SUB-SIN-CULIACAN", "SUB-SIN-MAZATLAN",
        NivelTension.KV_230, 185, 350, 2, ["Sinaloa"]
    ),
    LineaTransmision(
        "LT-230-CHI-DEL", "Chihuahua - Delicias 230kV",
        "SUB-CHI-CHIHUAHUA", "SUB-CHI-DELICIAS",
        NivelTension.KV_230, 95, 350, 1, ["Chihuahua"]
    ),
    LineaTransmision(
        "LT-230-TOP-MOCH", "Topolobampo - Los Mochis 230kV",
        "SUB-SIN-TOPOLOBAMPO", "SUB-SIN-MOCHIS",
        NivelTension.KV_230, 22, 600, 2, ["Sinaloa"]
    ),
]


# === RESUMEN POR ESTADO ===
def resumen_por_estado() -> dict:
    """Genera un resumen de capacidad instalada por estado."""
    resumen = {}
    for est in EstadoMX:
        plantas = [p for p in PLANTAS_GENERACION if p.estado == est]
        cap_total = sum(p.capacidad_mw for p in plantas)
        subs = [s for s in SUBESTACIONES if s.estado == est]
        resumen[est.value] = {
            "plantas": len(plantas),
            "capacidad_total_mw": cap_total,
            "subestaciones": len(subs),
            "tipos": list(set(p.tipo.value for p in plantas)),
        }
    return resumen


def get_planta_by_id(plant_id: str) -> CentralGeneracion | None:
    """Busca una planta por su ID."""
    for p in PLANTAS_GENERACION:
        if p.id == plant_id:
            return p
    return None


def get_subestacion_by_id(sub_id: str) -> Subestacion | None:
    """Busca una subestación por su ID."""
    for s in SUBESTACIONES:
        if s.id == sub_id:
            return s
    return None


def get_lineas_por_estado(estado: EstadoMX) -> list[LineaTransmision]:
    """Obtiene líneas que cruzan un estado."""
    return [lt for lt in LINEAS_TRANSMISION if estado.value in lt.estados_cruza]
